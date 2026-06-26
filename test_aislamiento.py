"""Test de aislamiento de datos entre usuarios.

Garantía del sistema multi-usuario: el agente, en cada sesión, solo ve y toca los
datos del usuario que está escribiendo (se fija con set_user_context → contextvar
user_id, y TODA query filtra por él). Este test crea dos usuarios con datos propios
y verifica que ninguno ve ni puede borrar lo del otro. Si alguna query nueva olvida
filtrar por user_id, este test debe fallar.

Uso:  DATABASE_PATH=/tmp/aisla.db python3 test_aislamiento.py
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_PATH", "/tmp/kontos_aislamiento.db")
# DB limpia para el test.
if os.path.exists(os.environ["DATABASE_PATH"]):
    os.remove(os.environ["DATABASE_PATH"])

from dotenv import load_dotenv
load_dotenv()

from db import init_db, get_conn
from context import set_user_context
from tools.gastos import registrar_gasto, listar_gastos, consultar_total, eliminar_gasto
from tools.despensa import agregar_producto_despensa, listar_productos_despensa
from tools.presupuestos import crear_presupuesto, ver_presupuestos
from tools.analisis import resumen_financiero

A, B = "1001", "2002"   # dos usuarios distintos
fallos = []


def check(cond, msg):
    print(("✅" if cond else "❌"), msg)
    if not cond:
        fallos.append(msg)


def main():
    init_db()

    # ── Usuario A siembra sus datos ──────────────────────────────────────────
    set_user_context(A, "Ana")
    registrar_gasto.invoke({"concepto": "Cafe de Ana", "monto": 50, "categoria": "Comida"})
    agregar_producto_despensa.invoke({"nombre": "Leche de Ana"})
    crear_presupuesto.invoke({"categoria": "Comida", "monto_limite": 1000})

    # ── Usuario B siembra los suyos ──────────────────────────────────────────
    set_user_context(B, "Beto")
    registrar_gasto.invoke({"concepto": "Taco de Beto", "monto": 80, "categoria": "Comida"})
    agregar_producto_despensa.invoke({"nombre": "Pan de Beto"})

    # ── Como B: no debe ver NADA de A ────────────────────────────────────────
    g = listar_gastos.invoke({})
    check("Taco de Beto" in g and "Cafe de Ana" not in g, "listar_gastos: B ve lo suyo, no lo de A")

    p = listar_productos_despensa.invoke({})
    check("Pan de Beto" in p and "Leche de Ana" not in p, "listar_productos: B ve lo suyo, no lo de A")

    t = consultar_total.invoke({})
    check("80" in t and "Cafe de Ana" not in t, "consultar_total: solo cuenta gastos de B")

    pre = ver_presupuestos.invoke({})
    check("No tienes presupuestos" in pre, "ver_presupuestos: B no ve el presupuesto de A")

    r = resumen_financiero.invoke({})
    check("$80.00" in r and "$130" not in r, "resumen_financiero: total de B = 80, sin mezclar a A")

    # ── Como B: no puede BORRAR un gasto de A (aunque adivine el id) ──────────
    with get_conn() as conn:
        id_a = conn.execute(
            "SELECT id FROM movimientos WHERE user_id=? AND concepto='Cafe de Ana'", (A,)
        ).fetchone()[0]
    set_user_context(B, "Beto")
    res = eliminar_gasto.invoke({"id": id_a})
    check("No se encontró" in res or "❌" in res, "eliminar_gasto: B NO puede borrar el gasto de A")
    with get_conn() as conn:
        sigue = conn.execute("SELECT COUNT(*) FROM movimientos WHERE id=?", (id_a,)).fetchone()[0]
    check(sigue == 1, "el gasto de A sigue intacto tras el intento de B")

    # ── Sesión sin usuario: no debe filtrar datos de nadie (fail-closed) ──────
    set_user_context("", "")
    g_vacio = listar_gastos.invoke({})
    check("Cafe de Ana" not in g_vacio and "Taco de Beto" not in g_vacio,
          "sin user_id en sesión: no se filtra ningún dato (fail-closed)")

    print()
    if fallos:
        print(f"💥 {len(fallos)} fallo(s) de aislamiento.")
        sys.exit(1)
    print("🎉 Aislamiento OK: cada usuario solo ve y toca sus propios datos.")


if __name__ == "__main__":
    main()
