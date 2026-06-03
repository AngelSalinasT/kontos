from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import get_user_id, get_username


def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@tool
def registrar_gasto_fijo(concepto: str, monto: float, periodicidad: str = "mensual", categoria: str = "General", fecha_inicio: Optional[str] = None) -> str:
    """Registra un gasto fijo o recurrente (renta, servicios, suscripciones, pagos mensuales).
    Úsala cuando el usuario mencione un pago que se repite regularmente.

    Args:
        concepto: Nombre del gasto (ej: 'Cable + Internet', 'Netflix')
        monto: Monto en pesos
        periodicidad: 'mensual', 'quincenal' o 'semanal'
        categoria: Servicios, Entretenimiento, Salud, General, etc.
        fecha_inicio: Fecha inicio YYYY-MM-DD; usa hoy si no se indica
    """
    user_id = get_user_id()
    with get_conn() as conn:
        upsert_usuario(conn, user_id, get_username())
        cat_id = get_or_create_categoria(conn, categoria, "gasto")
        conn.execute(
            "INSERT INTO gastos_fijos (user_id, categoria_id, concepto, monto, fecha_inicio, periodicidad) VALUES (?,?,?,?,?,?)",
            (user_id, cat_id, concepto, monto, fecha_inicio or _hoy(), periodicidad),
        )
    return f"✅ Gasto fijo: {concepto} ${monto:.2f} — {periodicidad}"


@tool
def listar_gastos_fijos() -> str:
    """Lista todos los gastos fijos del usuario.
    Úsala cuando el usuario pregunte por sus gastos fijos, pagos recurrentes o compromisos mensuales.
    """
    user_id = get_user_id()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT gf.id, gf.concepto, gf.monto, c.nombre, gf.periodicidad
               FROM gastos_fijos gf LEFT JOIN categorias c ON gf.categoria_id = c.id
               WHERE gf.user_id = ? ORDER BY gf.id""", (user_id,)
        ).fetchall()
    if not rows:
        return "ℹ️ No tienes gastos fijos registrados."
    total = sum(r["monto"] for r in rows)
    lines = [f"ID:{r['id']} {r['concepto']} | ${r['monto']:.2f} | {r['periodicidad']}" for r in rows]
    return f"📋 Gastos fijos ({len(rows)}):\n" + "\n".join(lines) + f"\n\nTotal mensual: ${total:.2f}"


@tool
def editar_gasto_fijo(id: int, concepto: Optional[str] = None, monto: Optional[float] = None, periodicidad: Optional[str] = None, categoria: Optional[str] = None) -> str:
    """Edita un gasto fijo por su ID. Usa listar_gastos_fijos primero si el usuario no sabe el ID.

    Args:
        id: ID del gasto fijo
        concepto: Nuevo nombre (opcional)
        monto: Nuevo monto (opcional)
        periodicidad: Nueva periodicidad (opcional)
        categoria: Nueva categoría (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []
    with get_conn() as conn:
        if concepto: campos.append("concepto = ?"); valores.append(concepto)
        if monto is not None: campos.append("monto = ?"); valores.append(monto)
        if periodicidad: campos.append("periodicidad = ?"); valores.append(periodicidad)
        if categoria:
            cat_id = get_or_create_categoria(conn, categoria, "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos: return "❌ No se indicó ningún campo a modificar."
        valores.extend([id, user_id])
        cur = conn.execute(f"UPDATE gastos_fijos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
    return f"✅ Gasto fijo {id} actualizado." if cur.rowcount else f"❌ No encontré el gasto fijo ID {id}."


@tool
def eliminar_gasto_fijo(id: int) -> str:
    """Elimina un gasto fijo por su ID.

    Args:
        id: ID del gasto fijo a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM gastos_fijos WHERE id = ? AND user_id = ?", (id, user_id))
    return f"🗑️ Gasto fijo {id} eliminado." if cur.rowcount else f"❌ No encontré el gasto fijo ID {id}."


@tool
def registrar_ingreso_fijo(concepto: str, monto: float, periodicidad: str = "mensual", categoria: str = "Ingresos", fecha_inicio: Optional[str] = None) -> str:
    """Registra un ingreso fijo o recurrente (sueldo, pensión, renta cobrada).
    Úsala cuando el usuario mencione un ingreso que recibe de forma regular.

    Args:
        concepto: Nombre del ingreso (ej: 'Nómina RAVIDZA', 'Pensión abuela')
        monto: Monto en pesos
        periodicidad: 'mensual', 'quincenal' o 'semanal'
        categoria: Salario, Ingresos, etc.
        fecha_inicio: Fecha inicio YYYY-MM-DD
    """
    user_id = get_user_id()
    with get_conn() as conn:
        upsert_usuario(conn, user_id, get_username())
        cat_id = get_or_create_categoria(conn, categoria, "ingreso")
        conn.execute(
            "INSERT INTO ingresos_fijos (user_id, categoria_id, concepto, monto, fecha_inicio, periodicidad) VALUES (?,?,?,?,?,?)",
            (user_id, cat_id, concepto, monto, fecha_inicio or _hoy(), periodicidad),
        )
    return f"✅ Ingreso fijo: {concepto} ${monto:.2f} — {periodicidad}"


@tool
def listar_ingresos_fijos() -> str:
    """Lista todos los ingresos fijos del usuario.
    Úsala cuando el usuario pregunte por sus ingresos, sueldo o entradas de dinero recurrentes.
    """
    user_id = get_user_id()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT inf.id, inf.concepto, inf.monto, inf.periodicidad
               FROM ingresos_fijos inf WHERE inf.user_id = ? ORDER BY inf.id""", (user_id,)
        ).fetchall()
    if not rows:
        return "ℹ️ No tienes ingresos fijos registrados."
    total = sum(r["monto"] for r in rows)
    lines = [f"ID:{r['id']} {r['concepto']} | ${r['monto']:.2f} | {r['periodicidad']}" for r in rows]
    return f"💰 Ingresos fijos ({len(rows)}):\n" + "\n".join(lines) + f"\n\nTotal mensual: ${total:.2f}"


@tool
def editar_ingreso_fijo(id: int, concepto: Optional[str] = None, monto: Optional[float] = None, periodicidad: Optional[str] = None) -> str:
    """Edita un ingreso fijo por su ID. Usa listar_ingresos_fijos primero si el usuario no sabe el ID.

    Args:
        id: ID del ingreso fijo
        concepto: Nuevo nombre (opcional)
        monto: Nuevo monto (opcional)
        periodicidad: Nueva periodicidad (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []
    if concepto: campos.append("concepto = ?"); valores.append(concepto)
    if monto is not None: campos.append("monto = ?"); valores.append(monto)
    if periodicidad: campos.append("periodicidad = ?"); valores.append(periodicidad)
    if not campos: return "❌ No se indicó ningún campo a modificar."
    valores.extend([id, user_id])
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE ingresos_fijos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
    return f"✅ Ingreso fijo {id} actualizado." if cur.rowcount else f"❌ No encontré el ingreso fijo ID {id}."


@tool
def eliminar_ingreso_fijo(id: int) -> str:
    """Elimina un ingreso fijo por su ID.

    Args:
        id: ID del ingreso fijo a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM ingresos_fijos WHERE id = ? AND user_id = ?", (id, user_id))
    return f"🗑️ Ingreso fijo {id} eliminado." if cur.rowcount else f"❌ No encontré el ingreso fijo ID {id}."
