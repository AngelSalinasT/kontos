import os
import logging
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario
from context import get_user_id, get_username, get_imagen_path
from tools.despensa import _recalcular_patron

logger = logging.getLogger(__name__)


def _ocr_imagen(imagen_path: str) -> str:
    try:
        import easyocr
        reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
        return "\n".join(easyocr.Reader(["es", "en"], gpu=False, verbose=False).readtext(imagen_path, detail=0))
    except ImportError:
        pass
    try:
        from PIL import Image
        import pytesseract
        return pytesseract.image_to_string(Image.open(imagen_path), lang="spa")
    except Exception as e:
        return f"ERROR_OCR: {e}"


@tool
def procesar_ticket() -> str:
    """Procesa la foto de un ticket de compra con OCR y registra las compras en la despensa automáticamente.
    Úsala cuando el usuario envíe una foto de su ticket o recibo de compra.
    No necesita argumentos; la imagen ya está disponible en el contexto.
    """
    imagen_path = get_imagen_path()
    if not imagen_path or not os.path.exists(imagen_path):
        return "❌ No se recibió ninguna imagen de ticket válida."

    texto_ocr = _ocr_imagen(imagen_path)
    logger.info("OCR ticket (%d chars): %s", len(texto_ocr), texto_ocr[:300].replace("\n", " | "))
    if texto_ocr.startswith("ERROR_OCR"):
        logger.error("Fallo OCR: %s", texto_ocr)
        return f"❌ No pude leer la imagen. Instala easyocr.\n{texto_ocr}"

    hoy = datetime.now().strftime("%Y-%m-%d")
    user_id = get_user_id()
    username = get_username()

    from langchain_google_genai import ChatGoogleGenerativeAI
    from utils.json_parser import parse_json_from_text

    _llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
    )

    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        catalogo = conn.execute("SELECT id, nombre FROM productos WHERE user_id = ? AND activo = 1", (user_id,)).fetchall()

    nombres_catalogo = [r["nombre"] for r in catalogo]
    prompt = f"""Analiza este ticket y extrae los productos. Mapea al catálogo del usuario cuando coincida.
Catálogo: {nombres_catalogo}
Ticket:
---
{texto_ocr[:3000]}
---
Responde SOLO con JSON:
{{"tienda": "string o null", "fecha": "YYYY-MM-DD (usa {hoy} si no aparece)", "total": float o null,
  "productos": [{{"nombre_catalogo": "nombre exacto del catálogo o null", "nombre_ticket": "como aparece", "precio": float o null, "cantidad": float}}]}}"""

    resp = _llm.invoke(prompt)
    raw = resp.content if hasattr(resp, "content") else str(resp)
    data = parse_json_from_text(raw)
    if not data:
        logger.warning("No se pudo parsear JSON del ticket. Respuesta LLM: %s", str(raw)[:500])
        return "❌ No pude interpretar el ticket. Intenta con una foto más nítida."
    logger.info("Ticket parseado: tienda=%s total=%s productos=%d",
                data.get("tienda"), data.get("total"), len(data.get("productos", [])))

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tickets_ocr (user_id, fecha, tienda, total, imagen_path, procesado) VALUES (?,?,?,?,?,1)",
            (user_id, data.get("fecha", hoy), data.get("tienda"), data.get("total"), imagen_path),
        )
        ticket_id = cur.lastrowid
        cat_map = {r["nombre"].lower(): r["id"] for r in catalogo}
        registradas, ignoradas = [], []
        for item in data.get("productos", []):
            nombre_cat = item.get("nombre_catalogo")
            if not nombre_cat:
                ignoradas.append(item.get("nombre_ticket", "?")); continue
            producto_id = cat_map.get(nombre_cat.lower())
            if not producto_id:
                ignoradas.append(item.get("nombre_ticket", "?")); continue
            conn.execute(
                "INSERT INTO compras_despensa (producto_id, user_id, ticket_id, fecha, precio, cantidad, tienda, fuente) VALUES (?,?,?,?,?,?,?,'ocr')",
                (producto_id, user_id, ticket_id, data.get("fecha", hoy), item.get("precio"), item.get("cantidad", 1), data.get("tienda")),
            )
            _recalcular_patron(conn, producto_id)
            registradas.append(nombre_cat)

    respuesta = f"🧾 Ticket — {data.get('tienda', 'tienda desconocida')}\n"
    if data.get("total"): respuesta += f"Total: ${data['total']:.2f}\n"
    if registradas: respuesta += f"\n✅ Registradas ({len(registradas)}):\n" + "\n".join(f"• {n}" for n in registradas)
    if ignoradas: respuesta += f"\n⚠️ No encontrados ({len(ignoradas)}):\n" + "\n".join(f"• {n}" for n in ignoradas) + "\n\nAgrega los faltantes con 'agregar producto'."
    return respuesta


@tool
def listar_tickets() -> str:
    """Lista los tickets de compra escaneados. Úsala cuando el usuario quiera ver sus tickets procesados."""
    user_id = get_user_id()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, fecha, tienda, total, procesado FROM tickets_ocr WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (user_id,),
        ).fetchall()
    if not rows: return "ℹ️ No hay tickets escaneados."
    lines = [
        f"{'✅' if r['procesado'] else '⏳'} ID:{r['id']} {r['fecha']} | {r['tienda'] or '—'} | " +
        (f"${r['total']:.2f}" if r['total'] else "—")
        for r in rows
    ]
    return "🧾 Tickets:\n" + "\n".join(lines)


@tool
def eliminar_ticket(id: int) -> str:
    """Elimina un ticket y todas sus compras asociadas.

    Args:
        id: ID del ticket a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        conn.execute("DELETE FROM compras_despensa WHERE ticket_id = ? AND user_id = ?", (id, user_id))
        cur = conn.execute("DELETE FROM tickets_ocr WHERE id = ? AND user_id = ?", (id, user_id))
    return f"🗑️ Ticket {id} eliminado." if cur.rowcount else f"❌ No encontré el ticket ID {id}."
