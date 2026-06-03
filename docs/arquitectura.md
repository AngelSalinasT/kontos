# Arquitectura de Kontos

Bot de Telegram para finanzas y despensa, sobre un agente **ReAct** de LangGraph
(`create_react_agent`) con Gemini 2.5 Flash y 30 herramientas en 5 dominios.

![Arquitectura de Kontos](arquitectura.png)

> El PNG se regenera con `mmdc` a partir del diagrama Mermaid de abajo.
> El grafo interno crudo de LangGraph (start → agent ⇄ tools → end) está en `grafo_langgraph.png`.

## Grafo de conversación

> El filtro de whitelist (`_autorizado`) corre **antes** de cualquier procesamiento:
> si el usuario no está autorizado se rechaza sin descargar la foto, transcribir audio ni llamar a Gemini.

```mermaid
flowchart TD
    TG([Telegram]) --> AUTH{_autorizado?<br/>whitelist}
    AUTH -->|no| REJ[⛔ rechazar · sin procesar nada]
    AUTH -->|sí| H{Tipo de mensaje}

    H -->|texto| HT[handle_text]
    H -->|voz/audio| HV[handle_voice<br/>Whisper → texto]
    H -->|foto| HP[handle_photo<br/>descarga img + caption]

    HT --> BS[_build_state<br/>historial 20 msgs + contexto user]
    HV --> BS
    HP --> BS

    BS --> CTX[(context.py<br/>user_id, username,<br/>imagen_path, es_voz)]
    BS --> AGENT

    subgraph LG[LangGraph · create_react_agent]
        AGENT[🧠 Gemini 2.5 Flash<br/>temperature=0<br/>SYSTEM_PROMPT] -->|tool_call| TOOLS{ALL_TOOLS · 30}
        TOOLS -->|ToolMessage| AGENT
    end

    TOOLS --- G1[💸 gastos ×5]
    TOOLS --- G2[🔁 fijos ×8]
    TOOLS --- G3[🛒 despensa ×10]
    TOOLS --- G4[📊 presupuestos ×4]
    TOOLS --- G5[🧾 tickets ×3<br/>OCR easyocr→Gemini]

    AGENT -->|mensaje final| RESP[_invocar_y_responder]
    RESP --> SAVE[(guardar_mensaje<br/>inbound+outbound)]
    RESP --> OUT([reply_text → Telegram])

    G3 -.-> DB[(gastos.db · SQLite)]
    G5 -.-> DB
    G1 -.-> DB
    G2 -.-> DB
    G4 -.-> DB
```

## Camino de un ticket (OCR)

```
foto → handle_photo → caption "procesar ticket" → agente decide → procesar_ticket()
  → _ocr_imagen (easyocr es+en)  ──► texto OCR
  → Gemini: "extrae productos como JSON"  ──► parse_json_from_text()
  → si data=None → "❌ No pude interpretar"   (fallo silencioso)
  → si OK → INSERT tickets_ocr + compras_despensa → "🧾 Ticket registrado"
```

## Herramientas por dominio (`tools/ALL_TOOLS`)

| Dominio | Módulo | Herramientas |
|---|---|---|
| 💸 Gastos | `tools/gastos.py` | registrar, listar, editar, eliminar, consultar_total |
| 🔁 Fijos | `tools/fijos.py` | gastos fijos (CRUD) + ingresos fijos (CRUD) |
| 🛒 Despensa | `tools/despensa.py` | productos (CRUD), compras (CRUD), lista, predicción |
| 📊 Presupuestos | `tools/presupuestos.py` | crear, ver, editar, eliminar |
| 🧾 Tickets | `tools/tickets.py` | procesar (OCR), listar, eliminar |

## Despliegue

- Host: `archlinux` (Tailscale `100.72.31.71`), `~/kontos`.
- Servicio: **systemd** `kontos.service` (no Docker), venv en `~/kontos/venv`.
- Datos: `gastos.db` (SQLite local).
