"""
Pruebas del flujo completo del grafo Kontos.
Requiere GEMINI_API_KEY y TELEGRAM_BOT_TOKEN en .env

Uso: python3 test_graph.py
"""
from dotenv import load_dotenv
load_dotenv()

from graph import graph
from langchain_core.messages import HumanMessage

TEST_USER_ID = "test_user_local"
TEST_USERNAME = "tester"


def run(texto: str, decision: str = None) -> str:
    state = {
        "messages": [HumanMessage(content=texto)],
        "user_id": TEST_USER_ID,
        "username": TEST_USERNAME,
        "decision": decision,
        "parsed_data": None,
        "final_response": None,
        "imagen_path": None,
        "es_voz": False,
    }
    result = graph.invoke(state)
    return result.get("final_response", "")


def test(label: str, texto: str, decision: str = None):
    print(f"\n🧪 {label}")
    try:
        resp = run(texto, decision)
        print(f"✅ {resp[:200]}")
    except Exception as e:
        print(f"❌ {e}")
    print("-" * 50)


if __name__ == "__main__":
    print("=" * 50)
    print("Kontos — pruebas de flujo completo")
    print("=" * 50)

    # ── Finanzas ──────────────────────────────────────
    test("Registrar gasto",         "Gasté $385 en Soriana hoy")
    test("Registrar gasto fijo",    "Agrega gasto fijo renta $5000 mensual")
    test("Registrar ingreso fijo",  "Agrega ingreso fijo sueldo $25000 mensual")
    test("Consultar total",         "Cuánto gasté este mes")
    test("Listar gastos",           "ver gastos")
    test("Listar gastos fijos",     "listar gastos fijos")
    test("Listar ingresos fijos",   "listar ingresos fijos")
    test("Presupuesto — crear",     "crear presupuesto comida $3000")
    test("Presupuesto — ver",       "cómo voy")

    # ── Despensa ──────────────────────────────────────
    test("Producto — crear",        "agregar producto Leche Kirkland despensa caja $428")
    test("Producto — listar",       "ver despensa")
    test("Compra — registrar",      "compré leche kirkland $428 en Costco")
    test("Compra — listar",         "historial compras")
    test("Lista de despensa",       "lista de despensa")
    test("Predicción",              "cuándo compro la leche")

    # ── Ayuda ──────────────────────────────────────────
    test("Ayuda general",           "qué puedes hacer")
