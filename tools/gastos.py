from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import get_user_id, get_username


def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@tool
def registrar_gasto(
    concepto: str,
    monto: float,
    categoria: str = "General",
    fecha: Optional[str] = None,
) -> str:
    """Registra un gasto o pago en la base de datos.
    Úsala cuando el usuario diga que pagó, gastó o compró algo con monto.
    Infiere la categoría: Comida, Transporte, Entretenimiento, Servicios, Salud, Compras, General.
    La fecha debe estar en formato YYYY-MM-DD; si no se menciona, usa la de hoy.

    Args:
        concepto: Descripción del gasto (ej: 'Uber Eats', 'Gasolina Pemex')
        monto: Monto en pesos mexicanos, mayor que cero
        categoria: Categoría inferida del concepto
        fecha: Fecha en YYYY-MM-DD; omitir si no se menciona
    """
    fecha = fecha or _hoy()
    user_id = get_user_id()
    username = get_username()

    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        cat_id = get_or_create_categoria(conn, categoria, "gasto")
        conn.execute(
            "INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen) VALUES (?,?,?,?,?,?,'telegram')",
            (user_id, username, fecha, concepto, monto, cat_id),
        )

    return f"✅ Registrado: {concepto} ${monto:.2f} [{categoria}] — {fecha}"


@tool
def listar_gastos(
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    categoria: Optional[str] = None,
) -> str:
    """Lista los gastos del usuario. Sin filtros muestra el mes actual.
    Úsala cuando el usuario pida ver, listar o consultar sus gastos.

    Args:
        mes: Mes numérico 1-12. Si no se indica, usa el mes actual.
        anio: Año de 4 dígitos. Si no se indica, usa el año actual.
        categoria: Filtrar por categoría específica (opcional).
    """
    now = datetime.now()
    mes = mes or now.month
    anio = anio or now.year
    user_id = get_user_id()

    inicio = f"{anio}-{mes:02d}-01"
    fin_mes = mes % 12 + 1
    fin_anio = anio if mes < 12 else anio + 1
    fin = f"{fin_anio}-{fin_mes:02d}-01"

    query = """
        SELECT m.id, m.fecha, m.concepto, m.monto, c.nombre
        FROM movimientos m
        LEFT JOIN categorias c ON m.categoria_id = c.id
        WHERE m.user_id = ? AND m.fecha >= ? AND m.fecha < ?
    """
    params = [user_id, inicio, fin]
    if categoria:
        query += " AND c.nombre LIKE ?"; params.append(f"%{categoria}%")
    query += " ORDER BY m.fecha DESC, m.id DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return f"ℹ️ No hay gastos registrados para {mes:02d}/{anio}."

    total = sum(r["monto"] for r in rows)
    lines = [f"ID:{r['id']} {r['fecha']} | {r['concepto']} | ${r['monto']:.2f} | {r['nombre'] or 'General'}" for r in rows]
    return f"📋 Gastos {mes:02d}/{anio} ({len(rows)}):\n" + "\n".join(lines) + f"\n\nTotal: ${total:.2f}"


@tool
def editar_gasto(
    id: int,
    concepto: Optional[str] = None,
    monto: Optional[float] = None,
    categoria: Optional[str] = None,
    fecha: Optional[str] = None,
) -> str:
    """Edita un gasto existente por su ID.
    Si el usuario no sabe el ID, usa listar_gastos primero.

    Args:
        id: ID del gasto a editar
        concepto: Nuevo concepto (opcional)
        monto: Nuevo monto (opcional)
        categoria: Nueva categoría (opcional)
        fecha: Nueva fecha YYYY-MM-DD (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []

    with get_conn() as conn:
        if concepto:
            campos.append("concepto = ?"); valores.append(concepto)
        if monto is not None:
            campos.append("monto = ?"); valores.append(monto)
        if fecha:
            campos.append("fecha = ?"); valores.append(fecha)
        if categoria:
            cat_id = get_or_create_categoria(conn, categoria, "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos:
            return "❌ No se indicó ningún campo a modificar."
        valores.extend([id, user_id])
        cur = conn.execute(
            f"UPDATE movimientos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores
        )

    return f"✅ Gasto {id} actualizado." if cur.rowcount else f"❌ No se encontró el gasto ID {id}."


@tool
def eliminar_gasto(id: int) -> str:
    """Elimina un gasto por su ID. Usa listar_gastos primero si el usuario no sabe el ID.

    Args:
        id: ID del gasto a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM movimientos WHERE id = ? AND user_id = ?", (id, user_id))
    return f"🗑️ Gasto {id} eliminado." if cur.rowcount else f"❌ No se encontró el gasto ID {id}."


@tool
def consultar_total(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
) -> str:
    """Consulta el total de gastos por período, desglosado por categoría.
    Úsala cuando el usuario pregunte cuánto gastó, pida un reporte o resumen.
    Sin fechas muestra el mes actual.

    Args:
        desde: Fecha inicio YYYY-MM-DD (opcional)
        hasta: Fecha fin YYYY-MM-DD (opcional)
    """
    now = datetime.now()
    desde = desde or now.replace(day=1).strftime("%Y-%m-%d")
    hasta = hasta or now.strftime("%Y-%m-%d")
    user_id = get_user_id()

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.nombre, SUM(m.monto) as total
               FROM movimientos m LEFT JOIN categorias c ON m.categoria_id = c.id
               WHERE m.user_id = ? AND m.fecha BETWEEN ? AND ?
               GROUP BY c.nombre ORDER BY total DESC""",
            (user_id, desde, hasta),
        ).fetchall()
        total_general = conn.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM movimientos WHERE user_id = ? AND fecha BETWEEN ? AND ?",
            (user_id, desde, hasta),
        ).fetchone()[0]
        ingresos = conn.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM ingresos_fijos WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    if not rows:
        return f"ℹ️ No hay gastos del {desde} al {hasta}."

    lines = [f"  {r['nombre'] or 'General'}: ${r['total']:,.2f}" for r in rows]
    respuesta = f"📊 Gastos {desde} → {hasta}:\n" + "\n".join(lines)
    respuesta += f"\n\n💵 Total: ${total_general:,.2f}"
    if ingresos:
        balance = ingresos - total_general
        respuesta += f"\n💰 Ingresos fijos: ${ingresos:,.2f}\n📈 Balance: ${balance:,.2f}"
    return respuesta
