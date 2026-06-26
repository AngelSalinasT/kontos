"""Registro de lo extraído de una imagen y herramientas relacionadas.

`registrar_movimientos` / `registrar_ticket` son funciones planas que invoca el nodo
`extraer_imagen` para registrar de forma determinista (sin pasar por el agente).
`clasificar_imagen_pendiente` es la ÚNICA tool de imagen del agente: se usa solo cuando
la extracción fue ambigua, Ángel aclaró qué era, y hay que registrar los datos cacheados.
"""
import logging
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import (
    get_user_id, get_username, get_datos_imagen, set_datos_imagen, set_imagen_pendiente,
)
from tools.despensa import _recalcular_patron

logger = logging.getLogger(__name__)


def _catalogo(conn, user_id: str):
    return conn.execute(
        "SELECT id, nombre FROM productos WHERE user_id = ? AND activo = 1", (user_id,)
    ).fetchall()


def registrar_movimientos(user_id: str, username: str, data: dict) -> str:
    """Registra cada cargo de una captura bancaria como gasto. Devuelve un resumen en texto."""
    movs = data.get("movimientos") or []
    registrados, total = [], 0.0
    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        for m in movs:
            monto = m.get("monto")
            if monto is None or monto <= 0:
                continue
            concepto = (m.get("concepto") or "Cargo").strip()
            fecha = m.get("fecha")
            cat_id = get_or_create_categoria(conn, m.get("categoria") or "General", "gasto")
            conn.execute(
                "INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen) "
                "VALUES (?,?,?,?,?,?,'ocr')",
                (user_id, username, fecha, concepto, monto, cat_id),
            )
            registrados.append((fecha, concepto, monto, m.get("categoria") or "General"))
            total += monto

    if not registrados:
        return "No encontré cargos para registrar en la captura (quizá solo eran pagos o abonos)."
    lineas = [f"• {f} · {c} · ${mo:,.2f} [{cat}]" for f, c, mo, cat in registrados]
    return (f"Se registraron {len(registrados)} gasto(s) por un total de ${total:,.2f}:\n"
            + "\n".join(lineas))


def registrar_ticket(user_id: str, username: str, data: dict) -> str:
    """Registra los productos de un ticket en la despensa (no cuenta como gasto)."""
    tienda = data.get("tienda")
    total = data.get("total")
    fecha = data.get("fecha")
    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        catalogo = _catalogo(conn, user_id)
        cur = conn.execute(
            "INSERT INTO tickets_ocr (user_id, fecha, tienda, total, imagen_path, procesado) "
            "VALUES (?,?,?,?,?,1)",
            (user_id, fecha, tienda, total, None),
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
                "INSERT INTO compras_despensa (producto_id, user_id, ticket_id, fecha, precio, cantidad, tienda, fuente) "
                "VALUES (?,?,?,?,?,?,?,'ocr')",
                (producto_id, user_id, ticket_id, fecha, item.get("precio"), item.get("cantidad", 1), tienda),
            )
            _recalcular_patron(conn, producto_id)
            registradas.append(nombre_cat)

    partes = [f"Ticket de {tienda or 'tienda desconocida'}" + (f" (total ${total:,.2f}, no cuenta como gasto)" if total else "")]
    if registradas:
        partes.append(f"Despensa actualizada ({len(registradas)}): " + ", ".join(registradas))
    if ignoradas:
        partes.append(f"No están en la despensa ({len(ignoradas)}): " + ", ".join(ignoradas)
                      + ". Se pueden agregar con 'agregar producto'.")
    return "\n".join(partes)


@tool
def clasificar_imagen_pendiente(tipo: str) -> str:
    """Registra la última foto que quedó pendiente de aclarar, ya que Ángel dijo qué era.
    Úsala SOLO cuando el sistema indicó que una foto quedó pendiente (no se distinguía si era
    ticket o captura bancaria) y Ángel aclaró cuál es.

    Args:
        tipo: 'ticket' (ticket de compra → despensa) o 'banco' (captura bancaria → gastos).
    """
    data = get_datos_imagen()
    if not data:
        return "❌ No hay ninguna foto pendiente de clasificar."
    user_id, username = get_user_id(), get_username()
    t = (tipo or "").lower().strip()
    if t in ("ticket", "ticket_compra"):
        resumen = registrar_ticket(user_id, username, data)
    elif t in ("banco", "estado_cuenta", "movimientos", "gasto", "gasto_suelto"):
        resumen = registrar_movimientos(user_id, username, data)
    else:
        return "❌ Tipo no válido. Usa 'ticket' o 'banco'."
    set_datos_imagen(None)
    set_imagen_pendiente(False)
    return resumen


@tool
def listar_tickets() -> str:
    """Lista los tickets de compra escaneados. Úsala cuando Ángel quiera ver sus tickets procesados."""
    user_id = get_user_id()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, fecha, tienda, total, procesado FROM tickets_ocr WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (user_id,),
        ).fetchall()
    if not rows:
        return "ℹ️ No hay tickets escaneados."
    lines = [
        f"{'✅' if r['procesado'] else '⏳'} ID:{r['id']} {r['fecha']} | {r['tienda'] or '—'} | "
        + (f"${r['total']:.2f}" if r['total'] else "—")
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
