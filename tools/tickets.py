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
        return "\n".join(reader.readtext(imagen_path, detail=0))
    except ImportError:
        pass
    try:
        from PIL import Image
        import pytesseract
        return pytesseract.image_to_string(Image.open(imagen_path), lang="spa")
    except Exception as e:
        return f"ERROR_OCR: {e}"


@tool
def procesar_imagen() -> str:
    """Procesa una foto que envió el usuario (ticket de compra, estado de cuenta,
    captura de movimientos de tarjeta/banco, o comprobante de un pago) con OCR.
    Detecta automáticamente qué tipo de imagen es y la registra donde corresponde:
    - Ticket de compra de súper → productos en la despensa + el total como gasto.
    - Estado de cuenta / movimientos → cada cargo como gasto.
    - Un solo pago/comprobante → un gasto.
    Úsala SIEMPRE que el usuario mande una foto. No necesita argumentos; la imagen
    ya está disponible en el contexto.
    """
    imagen_path = get_imagen_path()
    if not imagen_path or not os.path.exists(imagen_path):
        return "❌ No se recibió ninguna imagen válida."

    texto_ocr = _ocr_imagen(imagen_path)
    logger.info("OCR imagen (%d chars): %s", len(texto_ocr), texto_ocr[:300].replace("\n", " | "))
    if texto_ocr.startswith("ERROR_OCR"):
        logger.error("Fallo OCR: %s", texto_ocr)
        return f"❌ No pude leer la imagen. Intenta con una foto más nítida.\n{texto_ocr}"

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
    prompt = f"""Eres un extractor de datos financieros. Analiza el texto OCR de una imagen que envió el usuario y clasifícala:
- "ticket_compra": ticket/recibo de compra en una tienda (súper, farmacia…) con lista de productos.
- "estado_cuenta": estado de cuenta o lista de varios movimientos/transacciones de tarjeta o banco.
- "gasto_suelto": comprobante de UN solo pago/cargo (transferencia, recibo de servicio, una compra individual).
- "desconocido": no se puede determinar o no es financiero.

Catálogo de despensa del usuario (mapea productos SOLO si es ticket_compra): {nombres_catalogo}

Texto OCR:
---
{texto_ocr[:3500]}
---

Responde SOLO con JSON válido, sin texto adicional:
{{"tipo": "ticket_compra|estado_cuenta|gasto_suelto|desconocido",
  "tienda": "nombre de la tienda o null",
  "fecha": "YYYY-MM-DD (usa {hoy} si no aparece)",
  "total": <número o null: total del ticket_compra>,
  "productos": [{{"nombre_catalogo": "nombre EXACTO del catálogo si coincide, si no null", "nombre_ticket": "como aparece", "precio": <número o null>, "cantidad": <número>}}],
  "movimientos": [{{"concepto": "descripción del cargo", "monto": <número positivo>, "fecha": "YYYY-MM-DD", "categoria": "Comida|Transporte|Entretenimiento|Servicios|Salud|Compras|General"}}]}}

Reglas: 'productos' solo para ticket_compra. 'movimientos' solo para estado_cuenta o gasto_suelto, e incluye ÚNICAMENTE cargos/gastos (NO pagos a la tarjeta, abonos, depósitos ni intereses a favor)."""

    resp = _llm.invoke(prompt)
    raw = resp.content if hasattr(resp, "content") else str(resp)
    data = parse_json_from_text(raw)
    if not data:
        logger.warning("No se pudo parsear JSON de la imagen. Respuesta LLM: %s", str(raw)[:500])
        return "❌ No pude interpretar la imagen. Intenta con una foto más nítida."

    tipo = (data.get("tipo") or "").lower()
    logger.info("Imagen clasificada como '%s' (tienda=%s total=%s productos=%d movimientos=%d)",
                tipo, data.get("tienda"), data.get("total"),
                len(data.get("productos") or []), len(data.get("movimientos") or []))

    if tipo == "ticket_compra":
        return _registrar_ticket(user_id, username, data, catalogo, imagen_path, hoy)
    if tipo in ("estado_cuenta", "gasto_suelto"):
        return _registrar_movimientos(user_id, username, data, hoy)
    return ("🤔 No logré identificar si es un ticket de compra o un estado de cuenta. "
            "¿Me dices qué es, o mandas una foto más clara?")


def _registrar_ticket(user_id, username, data, catalogo, imagen_path, hoy) -> str:
    """Ticket de súper: registra productos en la despensa y el total como gasto."""
    from db import get_or_create_categoria
    fecha = data.get("fecha") or hoy
    tienda = data.get("tienda")
    total = data.get("total")

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tickets_ocr (user_id, fecha, tienda, total, imagen_path, procesado) VALUES (?,?,?,?,?,1)",
            (user_id, fecha, tienda, total, imagen_path),
        )
        ticket_id = cur.lastrowid
        cat_map = {r["nombre"].lower(): r["id"] for r in catalogo}
        registradas, ignoradas = [], []
        for item in data.get("productos") or []:
            nombre_cat = item.get("nombre_catalogo")
            if not nombre_cat or nombre_cat.lower() not in cat_map:
                ignoradas.append(item.get("nombre_ticket", "?")); continue
            producto_id = cat_map[nombre_cat.lower()]
            conn.execute(
                "INSERT INTO compras_despensa (producto_id, user_id, ticket_id, fecha, precio, cantidad, tienda, fuente) VALUES (?,?,?,?,?,?,?,'ocr')",
                (producto_id, user_id, ticket_id, fecha, item.get("precio"), item.get("cantidad", 1), tienda),
            )
            _recalcular_patron(conn, producto_id)
            registradas.append(nombre_cat)

        # El ticket también es un gasto: registra el total en movimientos.
        gasto_registrado = False
        if total:
            cat_id = get_or_create_categoria(conn, "Despensa", "gasto")
            conn.execute(
                "INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen) VALUES (?,?,?,?,?,?,'ocr')",
                (user_id, username, fecha, f"Compra {tienda or 'súper'}", total, cat_id),
            )
            gasto_registrado = True

    respuesta = f"🧾 Ticket — {tienda or 'tienda desconocida'}\n"
    if total:
        respuesta += f"Total: ${total:.2f}"
        if gasto_registrado:
            respuesta += " (registrado como gasto 💸)"
        respuesta += "\n"
    if registradas:
        respuesta += f"\n✅ Despensa ({len(registradas)}):\n" + "\n".join(f"• {n}" for n in registradas)
    if ignoradas:
        respuesta += f"\n⚠️ No están en tu despensa ({len(ignoradas)}):\n" + "\n".join(f"• {n}" for n in ignoradas) + "\n\nAgrégalos con 'agregar producto' si quieres seguirlos."
    return respuesta


def _registrar_movimientos(user_id, username, data, hoy) -> str:
    """Estado de cuenta o gasto suelto: registra cada cargo como gasto en movimientos."""
    from db import get_or_create_categoria
    movs = data.get("movimientos") or []
    if not movs:
        return ("ℹ️ Detecté un estado de cuenta pero no encontré cargos para registrar "
                "(quizá solo había pagos o abonos). ¿Quieres que registre algo en específico?")

    registrados, total = [], 0.0
    with get_conn() as conn:
        for m in movs:
            monto = m.get("monto")
            concepto = (m.get("concepto") or "Cargo").strip()
            if monto is None or monto <= 0:
                continue
            fecha = m.get("fecha") or hoy
            cat_id = get_or_create_categoria(conn, m.get("categoria") or "General", "gasto")
            conn.execute(
                "INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen) VALUES (?,?,?,?,?,?,'ocr')",
                (user_id, username, fecha, concepto, monto, cat_id),
            )
            registrados.append((fecha, concepto, monto, m.get("categoria") or "General"))
            total += monto

    if not registrados:
        return "ℹ️ No encontré cargos válidos para registrar en la imagen."

    lines = [f"• {f} | {c} | ${mo:.2f} [{cat}]" for f, c, mo, cat in registrados]
    return (f"💸 Registré {len(registrados)} gasto(s):\n" + "\n".join(lines) +
            f"\n\nTotal: ${total:.2f}")


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
