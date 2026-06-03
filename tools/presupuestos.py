from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import get_user_id, get_username


@tool
def crear_presupuesto(categoria: str, monto_limite: float, periodo: str = "mensual") -> str:
    """Crea un presupuesto máximo para una categoría de gastos.
    Úsala cuando el usuario quiera poner un límite de gasto para una categoría.

    Args:
        categoria: Categoría (ej: 'Comida', 'Entretenimiento')
        monto_limite: Monto máximo en pesos
        periodo: 'mensual', 'quincenal' o 'semanal'
    """
    user_id = get_user_id()
    with get_conn() as conn:
        upsert_usuario(conn, user_id, get_username())
        cat_id = get_or_create_categoria(conn, categoria, "gasto")
        conn.execute("INSERT INTO presupuestos (user_id, categoria_id, monto_limite, periodo) VALUES (?,?,?,?)",
                     (user_id, cat_id, monto_limite, periodo))
    return f"✅ Presupuesto: {categoria} — ${monto_limite:.2f} {periodo}"


@tool
def ver_presupuestos() -> str:
    """Muestra los presupuestos y cuánto se ha gastado este mes en cada categoría.
    Úsala cuando el usuario quiera ver cómo va con sus presupuestos.
    """
    user_id = get_user_id()
    hoy = datetime.now()
    mes_inicio = hoy.replace(day=1).strftime("%Y-%m-%d")
    mes_fin = hoy.strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.id, c.nombre, p.monto_limite, p.periodo,
                      COALESCE((SELECT SUM(m.monto) FROM movimientos m
                                LEFT JOIN categorias mc ON m.categoria_id = mc.id
                                WHERE m.user_id = p.user_id AND mc.nombre = c.nombre
                                AND m.fecha BETWEEN ? AND ?), 0) as gastado
               FROM presupuestos p LEFT JOIN categorias c ON p.categoria_id = c.id
               WHERE p.user_id = ?""",
            (mes_inicio, mes_fin, user_id),
        ).fetchall()
    if not rows: return "ℹ️ No tienes presupuestos configurados."
    lines = []
    for r in rows:
        pct = (r["gastado"] / r["monto_limite"] * 100) if r["monto_limite"] else 0
        barra = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        alerta = " ⚠️" if pct >= 90 else ""
        lines.append(f"ID:{r['id']} {r['nombre']} [{r['periodo']}]{alerta}\n  {barra} {pct:.0f}%  ${r['gastado']:.2f} / ${r['monto_limite']:.2f}")
    return "📊 Presupuestos — " + mes_inicio[:7] + ":\n\n" + "\n\n".join(lines)


@tool
def editar_presupuesto(id: int, monto_limite: Optional[float] = None, periodo: Optional[str] = None, categoria: Optional[str] = None) -> str:
    """Edita un presupuesto por su ID. Usa ver_presupuestos primero si el usuario no sabe el ID.

    Args:
        id: ID del presupuesto
        monto_limite: Nuevo límite (opcional)
        periodo: Nueva periodicidad (opcional)
        categoria: Nueva categoría (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []
    with get_conn() as conn:
        if monto_limite is not None: campos.append("monto_limite = ?"); valores.append(monto_limite)
        if periodo: campos.append("periodo = ?"); valores.append(periodo)
        if categoria:
            cat_id = get_or_create_categoria(conn, categoria, "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos: return "❌ No se indicó ningún campo a modificar."
        valores.extend([id, user_id])
        cur = conn.execute(f"UPDATE presupuestos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
    return f"✅ Presupuesto {id} actualizado." if cur.rowcount else f"❌ No encontré el presupuesto ID {id}."


@tool
def eliminar_presupuesto(id: int) -> str:
    """Elimina un presupuesto por su ID.

    Args:
        id: ID del presupuesto a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM presupuestos WHERE id = ? AND user_id = ?", (id, user_id))
    return f"🗑️ Presupuesto {id} eliminado." if cur.rowcount else f"❌ No encontré el presupuesto ID {id}."
