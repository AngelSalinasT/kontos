import os
from typing import Dict, Any
from datetime import datetime
from db import get_conn, upsert_usuario
from utils.json_parser import parse_json_from_text
from nodes.despensa.compras import recalcular_patron


def _ocr_imagen(imagen_path: str) -> str:
    """Extrae texto de una imagen usando easyocr o pytesseract (fallback)."""
    try:
        import easyocr
        reader = easyocr.Reader(['es', 'en'], gpu=False)
        results = reader.readtext(imagen_path, detail=0)
        return "\n".join(results)
    except ImportError:
        pass
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(imagen_path)
        return pytesseract.image_to_string(img, lang='spa')
    except Exception as e:
        return f"ERROR_OCR: {e}"


def procesar_ticket_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Recibe la ruta de una imagen de ticket, aplica OCR y registra las compras
    de productos que ya existen en la despensa del usuario.
    """
    imagen_path = state.get("imagen_path")
    if not imagen_path or not os.path.exists(imagen_path):
        return {**state, "final_response": "❌ No se recibió ninguna imagen de ticket válida."}

    texto_ocr = _ocr_imagen(imagen_path)
    if texto_ocr.startswith("ERROR_OCR"):
        return {**state, "final_response": f"❌ No pude leer la imagen. Instala easyocr o pytesseract.\n{texto_ocr}"}

    hoy = datetime.now().strftime("%Y-%m-%d")
    user_id = state.get("user_id", "1234")
    username = state.get("username", "Desconocido")

    # Obtener catálogo del usuario para darle contexto al LLM
    with get_conn() as conn:
        catalogo = conn.execute(
            "SELECT id, nombre FROM productos WHERE user_id = ? AND activo = 1", (user_id,)
        ).fetchall()

    nombres_catalogo = [r["nombre"] for r in catalogo]

    prompt = f"""Analiza este texto de un ticket de compra y extrae los productos comprados.
Compara con el catálogo del usuario y mapea cada línea a un producto del catálogo si coincide.

Catálogo del usuario: {nombres_catalogo}

Texto del ticket:
---
{texto_ocr[:3000]}
---

Responde SOLO con un objeto JSON:
{{
    "tienda": "string o null",
    "fecha": "YYYY-MM-DD (usa {hoy} si no aparece)",
    "total": float o null,
    "productos": [
        {{"nombre_catalogo": "nombre exacto del catálogo o null si no coincide",
          "nombre_ticket": "como aparece en el ticket",
          "precio": float o null,
          "cantidad": float}}
    ]
}}"""

    data = parse_json_from_text(llm.invoke(prompt))
    if not data:
        return {**state, "final_response": "❌ No pude interpretar el ticket. Intenta con una foto más nítida."}

    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)

        # Guardar ticket
        cur = conn.execute(
            '''INSERT INTO tickets_ocr (user_id, fecha, tienda, total, imagen_path, procesado)
               VALUES (?, ?, ?, ?, ?, 1)''',
            (user_id, data.get("fecha", hoy), data.get("tienda"), data.get("total"), imagen_path)
        )
        ticket_id = cur.lastrowid

        # Crear mapa nombre → id del catálogo
        cat_map = {r["nombre"].lower(): r["id"] for r in catalogo}

        registradas, ignoradas = [], []
        for item in data.get("productos", []):
            nombre_cat = item.get("nombre_catalogo")
            if not nombre_cat:
                ignoradas.append(item.get("nombre_ticket", "?"))
                continue

            producto_id = cat_map.get(nombre_cat.lower())
            if not producto_id:
                ignoradas.append(item.get("nombre_ticket", "?"))
                continue

            conn.execute(
                '''INSERT INTO compras_despensa (producto_id, user_id, ticket_id, fecha, precio, cantidad, tienda, fuente)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ocr')''',
                (producto_id, user_id, ticket_id,
                 data.get("fecha", hoy), item.get("precio"),
                 item.get("cantidad", 1), data.get("tienda"))
            )
            recalcular_patron(conn, producto_id)
            registradas.append(nombre_cat)

    respuesta = f"🧾 Ticket procesado — {data.get('tienda', 'tienda desconocida')}\n"
    if data.get("total"):
        respuesta += f"Total: ${data['total']:.2f}\n"
    if registradas:
        respuesta += f"\n✅ Compras registradas ({len(registradas)}):\n" + "\n".join(f"• {n}" for n in registradas)
    if ignoradas:
        respuesta += f"\n⚠️ No encontrados en tu despensa ({len(ignoradas)}):\n" + "\n".join(f"• {n}" for n in ignoradas)
        respuesta += "\n\nAgrega los productos faltantes con 'agregar producto' para la próxima vez."

    return {**state, "final_response": respuesta}


def listar_tickets_node(state: Dict[str, Any]) -> Dict[str, Any]:
    user_id = state.get("user_id", "1234")
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT id, fecha, tienda, total, procesado, timestamp
               FROM tickets_ocr WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT 20''',
            (user_id,)
        ).fetchall()

    if not rows:
        return {**state, "final_response": "ℹ️ No hay tickets escaneados."}

    lines = []
    for r in rows:
        total = f"${r['total']:.2f}" if r['total'] else "—"
        estado = "✅" if r['procesado'] else "⏳"
        lines.append(f"{estado} ID:{r['id']} {r['fecha']} | {r['tienda'] or '—'} | {total}")

    return {**state, "final_response": "🧾 Tickets escaneados:\n" + "\n".join(lines)}


def eliminar_ticket_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere eliminar un ticket. Extrae el ID.
Responde SOLO con JSON: {{"id": número}}
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or "id" not in data:
        return {**state, "final_response": "❌ Indica el ID del ticket a eliminar."}

    user_id = state.get("user_id", "1234")
    with get_conn() as conn:
        # Las compras asociadas se eliminan en cascada (o manualmente)
        conn.execute(
            "DELETE FROM compras_despensa WHERE ticket_id = ? AND user_id = ?",
            (data["id"], user_id)
        )
        conn.execute(
            "DELETE FROM tickets_ocr WHERE id = ? AND user_id = ?",
            (data["id"], user_id)
        )

    return {**state, "final_response": f"🗑️ Ticket {data['id']} y sus compras asociadas eliminados."}
