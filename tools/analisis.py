"""Herramientas de análisis para que el agente razone con números EXACTOS.

`resumen_financiero` entrega el panorama del mes ya calculado (totales, balance,
presupuestos, avance del mes) para que el agente aconseje sin hacer aritmética.
`calcular` evalúa expresiones aritméticas de forma segura: los LLM se equivocan
con las matemáticas, así que cualquier cuenta debe pasar por aquí.
"""
import ast
import operator
from calendar import monthrange
from datetime import datetime
from langchain_core.tools import tool
from db import get_conn
from context import get_user_id


# ── Calculadora segura ────────────────────────────────────────────────────────
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("expresión no permitida")


@tool
def calcular(expresion: str) -> str:
    """Evalúa una expresión aritmética y devuelve el resultado exacto.
    Úsala SIEMPRE que necesites una cuenta (porcentajes, restas, divisiones, proyecciones):
    no calcules de cabeza. Solo números y operadores + - * / // % ** y paréntesis.

    Args:
        expresion: Operación aritmética, ej: '4200 / 6000 * 100' o '(5000 - 4200) / 20'
    """
    try:
        resultado = _eval(ast.parse(expresion, mode="eval").body)
        if isinstance(resultado, float):
            resultado = round(resultado, 2)
        return f"{expresion} = {resultado}"
    except Exception:
        return f"❌ No pude evaluar '{expresion}'. Usa solo números y + - * / // % ** ()."


# ── Resumen financiero del mes ────────────────────────────────────────────────
@tool
def resumen_financiero() -> str:
    """Panorama financiero del mes en curso, con todos los números ya calculados.
    Úsala como BASE para responder cómo va Ángel, dar el balance, o detectar alertas:
    trae el total gastado, el desglose por categoría, ingresos, gastos fijos, balance,
    el estado de cada presupuesto y cuánto del mes ha transcurrido. Razona sobre estos
    datos para aconsejar; no es una tabla para copiar tal cual.
    """
    user_id = get_user_id()
    hoy = datetime.now()
    mes_inicio = hoy.replace(day=1).strftime("%Y-%m-%d")
    hoy_str = hoy.strftime("%Y-%m-%d")
    dias_mes = monthrange(hoy.year, hoy.month)[1]
    dia_actual = hoy.day
    pct_mes = round(dia_actual / dias_mes * 100)

    with get_conn() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(monto),0) FROM movimientos WHERE user_id=? AND fecha BETWEEN ? AND ?",
            (user_id, mes_inicio, hoy_str),
        ).fetchone()[0]
        por_cat = conn.execute(
            """SELECT COALESCE(c.nombre,'General') cat, SUM(m.monto) t
               FROM movimientos m LEFT JOIN categorias c ON m.categoria_id=c.id
               WHERE m.user_id=? AND m.fecha BETWEEN ? AND ?
               GROUP BY c.nombre ORDER BY t DESC""",
            (user_id, mes_inicio, hoy_str),
        ).fetchall()
        ingresos = conn.execute(
            "SELECT COALESCE(SUM(monto),0) FROM ingresos_fijos WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        fijos = conn.execute(
            "SELECT COALESCE(SUM(monto),0) FROM gastos_fijos WHERE user_id=? AND concepto NOT LIKE '%MSI%'",
            (user_id,),
        ).fetchone()[0]
        presupuestos = conn.execute(
            """SELECT c.nombre cat, p.monto_limite lim,
                      COALESCE((SELECT SUM(m.monto) FROM movimientos m
                                LEFT JOIN categorias mc ON m.categoria_id=mc.id
                                WHERE m.user_id=p.user_id AND mc.nombre=c.nombre
                                AND m.fecha BETWEEN ? AND ?),0) gastado
               FROM presupuestos p LEFT JOIN categorias c ON p.categoria_id=c.id
               WHERE p.user_id=?""",
            (mes_inicio, hoy_str, user_id),
        ).fetchall()

    balance = ingresos - total - fijos
    L = [f"Mes en curso: {mes_inicio[:7]} · día {dia_actual}/{dias_mes} ({pct_mes}% del mes transcurrido)"]
    L.append(f"Gastado este mes (variable): ${total:,.2f}")
    if por_cat:
        L.append("Por categoría: " + "; ".join(f"{r['cat']} ${r['t']:,.2f}" for r in por_cat))
    L.append(f"Ingresos fijos: ${ingresos:,.2f} · Gastos fijos: ${fijos:,.2f} · Balance disponible: ${balance:,.2f}")
    if presupuestos:
        partes = []
        for r in presupuestos:
            pct = round(r["gastado"] / r["lim"] * 100) if r["lim"] else 0
            partes.append(f"{r['cat']} ${r['gastado']:,.2f}/${r['lim']:,.2f} ({pct}%)")
        L.append("Presupuestos: " + "; ".join(partes))
    else:
        L.append("Presupuestos: ninguno configurado")
    L.append("(Datos exactos. Compara el % gastado de cada presupuesto contra el % del mes "
             "transcurrido para detectar si el ritmo de gasto va alto. Usa `calcular` para cuentas.)")
    return "\n".join(L)
