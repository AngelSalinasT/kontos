"""
Smoke test completo del agente Kontos — sin Telegram.
Uso: python3 test_local.py
"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from graph import graph
from langchain_core.messages import HumanMessage


def run(texto, decision=None):
    state = {
        "messages": [HumanMessage(content=texto)],
        "user_id": "test_local",
        "username": "Angel",
        "decision": decision,
        "parsed_data": None,
        "final_response": None,
        "imagen_path": None,
        "es_voz": False,
    }
    return graph.invoke(state).get("final_response", "")


CASOS = [
    ("Finanzas — registrar gasto",     "Gasté $385 en Soriana hoy"),
    ("Finanzas — gasto fijo",          "Agrega gasto fijo renta $5000 mensual"),
    ("Finanzas — ingreso fijo",        "Agrega ingreso fijo sueldo $25000 mensual"),
    ("Finanzas — consultar total",     "Cuánto gasté este mes"),
    ("Finanzas — listar gastos",       "ver gastos"),
    ("Presupuesto — crear",            "crear presupuesto comida $3000"),
    ("Presupuesto — ver",              "cómo voy"),
    ("Despensa — crear producto",      "agregar producto Leche Kirkland categoría despensa precio 428"),
    ("Despensa — listar productos",    "ver despensa"),
    ("Despensa — registrar compra",    "compré leche kirkland $428 en Costco"),
    ("Despensa — lista de compras",    "lista de despensa"),
    ("Despensa — predicción",          "cuándo compro la leche"),
    ("Ayuda general",                  "qué puedes hacer"),
]

if __name__ == "__main__":
    print("Cargando grafo...")
    print("✅ Listo\n" + "=" * 55)

    ok = err = 0
    for label, texto in CASOS:
        try:
            resp = run(texto)
            print(f"✅  {label}")
            print(f"    {resp[:200]}")
            ok += 1
        except Exception as e:
            print(f"❌  {label}")
            print(f"    {e}")
            err += 1
        print()

    print("=" * 55)
    print(f"  {ok} OK  |  {err} ERROR")
