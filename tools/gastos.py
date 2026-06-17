import re
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import get_user_id, get_username

CATEGORIA_MSI = "Mensualidades"

# Detección de cargos a meses sin intereses (MSI).
_MSI_PLAZO_RE = re.compile(r"\b(\d{1,2})\s*de\s*(\d{1,2})\b")
_MSI_KW_RE = re.compile(r"(\bMSI\b|meses?\s+sin\s+inter\w*|mensualidad\w*)", re.IGNORECASE)


def _es_msi(concepto: str) -> bool:
    """True si el concepto parece un cargo a MSI: contiene 'MSI', 'meses sin
    intereses', 'mensualidad', o un plazo tipo 'X de N' (p.ej. '11 de 12')."""
    if not concepto:
        return False
    if _MSI_KW_RE.search(concepto):
        return True
    m = _MSI_PLAZO_RE.search(concepto)
    if m:
        n, total = int(m.group(1)), int(m.group(2))
        return 1 <= n <= total <= 48
    return False


def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _tabla_gastos(rows, total: float) -> str:
    """Tabla monoespaciada (4 columnas) envuelta en ``` para que Telegram la
    pinte como <pre> con columnas alineadas. El concepto se recorta a CONC_W."""
    ID_W, FECHA_W, CONC_W, MONTO_W = 3, 5, 14, 10

    def fila(idv, fecha, concepto, monto) -> str:
        return (f"{str(idv):>{ID_W}} {fecha:<{FECHA_W}} "
                f"{concepto[:CONC_W]:<{CONC_W}} {monto:>{MONTO_W}}")

    header = fila("ID", "Fecha", "Concepto", "Monto")
    sep = "─" * len(header)
    cuerpo = "\n".join(
        fila(r["id"], r["fecha"][5:], r["concepto"] or "", f"{r['monto']:,.2f}") for r in rows
    )
    label_w = ID_W + 1 + FECHA_W + 1 + CONC_W
    total_line = f"{'Total':>{label_w}} {total:>{MONTO_W},.2f}"
    return f"```\n{header}\n{sep}\n{cuerpo}\n{sep}\n{total_line}\n```"


def _tabla_categorias(rows, total: float) -> str:
    """Tabla monoespaciada (categoría · monto) envuelta en ``` para Telegram."""
    CAT_W, MONTO_W = 16, 11

    def fila(cat, monto) -> str:
        return f"{cat[:CAT_W]:<{CAT_W}} {monto:>{MONTO_W}}"

    header = fila("Categoría", "Monto")
    sep = "─" * len(header)
    cuerpo = "\n".join(fila(r["nombre"] or "General", f"{r['total']:,.2f}") for r in rows)
    total_line = fila("Total", f"{total:,.2f}")
    return f"```\n{header}\n{sep}\n{cuerpo}\n{sep}\n{total_line}\n```"


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
    # Detección automática de MSI: si no se forzó otra categoría y el concepto
    # parece una mensualidad, se etiqueta como Mensualidades (separa del gasto variable).
    if categoria == "General" and _es_msi(concepto):
        categoria = CATEGORIA_MSI
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
    # La tabla viene en un bloque ``` ya alineado: el modelo debe copiarla tal cual.
    return f"Gastos {mes:02d}/{anio} ({len(rows)}):\n" + _tabla_gastos(rows, total)


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
        # Gastos fijos: se restan al balance. Se excluyen los MSI porque esos ya
        # entran como movimientos (categoría Mensualidades) y se contarían doble.
        fijos = conn.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM gastos_fijos "
            "WHERE user_id = ? AND concepto NOT LIKE '%MSI%'",
            (user_id,),
        ).fetchone()[0]

    if not rows:
        return f"ℹ️ No hay gastos del {desde} al {hasta}."

    # La tabla viene en un bloque ``` ya alineado: el modelo debe copiarla tal cual.
    respuesta = f"Gastos {desde} → {hasta}:\n" + _tabla_categorias(rows, total_general)
    if ingresos:
        balance = ingresos - total_general - fijos
        respuesta += (
            f"\nIngresos: ${ingresos:,.2f} · Gastos fijos: -${fijos:,.2f}"
            f" · Balance: ${balance:,.2f}"
        )
    return respuesta
