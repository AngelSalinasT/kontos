# Kontos

Bot de Telegram para finanzas personales y gestión de despensa. Registra gastos, administra tu inventario del hogar y predice cuándo volver a comprar — todo en lenguaje natural, almacenado localmente.

---

## Características

**Finanzas**
- Registro de gastos con texto libre: `"Gasté $385 en Soriana hoy"`
- Gastos e ingresos fijos/recurrentes
- Consultas de totales por rango de fechas
- Presupuestos por categoría con barra de progreso

**Despensa**
- Catálogo de productos del hogar (Costco, supermercado, etc.)
- Registro de compras con cantidades y precios
- Lista de compras inteligente: cold-start para usuarios nuevos; predicción por patrones cuando hay historial suficiente
- Predicción de cuándo volver a comprar cada producto basada en el intervalo promedio real entre compras

**Medios**
- Fotos de tickets — OCR automático (easyocr) para extraer productos y montos
- Notas de voz — transcripción local con faster-whisper (CPU, sin GPU requerida)

---

## Tecnologías

| Componente | Tecnología |
|---|---|
| Bot | python-telegram-bot |
| Grafo de conversación | LangGraph + LangChain |
| LLM | Gemini 1.5 Flash (Google) |
| Base de datos | SQLite (local, sin servidor) |
| Voz | faster-whisper (modelo tiny, CPU) |
| OCR | easyocr + pytesseract (fallback) |

---

## Privacidad

Todo se almacena localmente en `gastos.db`. Las únicas llamadas externas son al API de Gemini (para el LLM) y a Telegram. No se usa ningún servicio de nube para datos personales.

---

## Instalación

```bash
git clone https://github.com/AngelSalinasT/kontos.git
cd kontos
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales:

```
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
GEMINI_API_KEY=tu_api_key_de_google_ai_studio
WHISPER_MODEL=tiny          # tiny | base | small | medium
```

### Cargar productos iniciales (opcional)

Si quieres pre-cargar un catálogo de productos de Costco:

```bash
python3 seed.py <tu_telegram_user_id>
```

Puedes obtener tu `user_id` enviando cualquier mensaje a [@userinfobot](https://t.me/userinfobot) en Telegram.

### Arrancar el bot

```bash
python3 bot.py
```

---

## Uso rápido

| Lo que escribes | Lo que hace |
|---|---|
| `Gasté $200 en gasolina` | Registra gasto |
| `Cuánto gasté este mes` | Total del mes actual |
| `Ver despensa` | Lista productos con predicción de resurtido |
| `Compré leche Kirkland $428` | Registra compra en despensa |
| `Lista de despensa` | Qué comprar en el siguiente viaje |
| `Crear presupuesto comida $3000` | Define presupuesto por categoría |
| `Cómo voy` | Estado de presupuestos con % de avance |
| _(foto de ticket)_ | OCR automático del ticket |
| _(nota de voz)_ | Transcribe y procesa como texto |

---

## Estructura del proyecto

```
kontos/
├── bot.py                  # Handlers de Telegram (texto, voz, foto)
├── db.py                   # Base de datos SQLite (11 tablas)
├── graph.py                # Grafo LangGraph (44 nodos)
├── seed.py                 # Carga inicial de productos Costco
├── nodes/
│   ├── despensa/
│   │   ├── compras.py      # CRUD compras + cálculo de patrones
│   │   ├── lista.py        # Lista inteligente y predicciones
│   │   ├── productos.py    # CRUD catálogo de productos
│   │   └── tickets.py      # OCR de tickets físicos
│   ├── gastos.py           # Registro y consulta de gastos
│   ├── gastos_fijos.py     # Gastos recurrentes
│   ├── historial.py        # Persistencia de mensajes (inbound/outbound)
│   ├── ingresos_fijos.py   # Ingresos recurrentes
│   ├── presupuestos.py     # CRUD presupuestos
│   ├── router.py           # Router por keywords + LLM fallback
│   └── total.py            # Consultas de totales
├── services/
│   └── whisper_service.py  # Transcripción de voz (CPU)
└── utils/
    └── json_parser.py      # Parser JSON robusto (centralizado)
```

---

## Licencia

MIT
