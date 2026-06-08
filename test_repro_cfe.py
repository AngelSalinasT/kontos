"""
Reproducción del bug del CFE alucinado.
Simula el flujo real del bot: historial con dos fotos YA procesadas (turnos pasados)
seguido de un mensaje de TEXTO sin foto ("¿cuáles son los gastos del mes?").

ANTES del fix: el modelo abría con "He procesado la imagen... se registró CFE $455"
              (inventaba un registro inexistente).
DESPUÉS del fix: debe responder solo con los gastos reales que devuelva listar_gastos,
              sin anunciar ningún registro nuevo.

Uso: python3 test_repro_cfe.py
"""
import os, sys, re
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from langchain_core.messages import HumanMessage, AIMessage
from context import set_user_context
from graph import graph

# Historial que reproduce el escenario: dos turnos de foto YA atendidos.
HISTORIAL = [
    HumanMessage(content="[foto de ticket]"),
    AIMessage(content="He procesado la imagen. Se registraron 4 gastos del 6 de junio:\n"
                      "• $405.20 de Uber Eats (Comida)\n• $271.00 de Pay pal*comisione (General)\n"
                      "• $162.00 de Pay pal*comisione (General)\n• $179.00 de Apple.com/bill (Servicios)"),
    HumanMessage(content="[foto de ticket]"),
    AIMessage(content="He procesado la imagen. Se registraron 5 gastos del 7 de junio:\n"
                      "• $224.46 en Paypal *cloudflar (Servicios)\n• $267.24 en Amazon mexico (Compras)\n"
                      "• $399.00 en Amazon mexico (Compras)\n• $518.90 en Stripe *amazon (Compras)\n"
                      "• $195.00 en Amazon mexico (Compras)"),
]

PREGUNTA = "Cuáles son los gastos del mes?"

# Contexto del turno actual: SIN imagen, sesión en curso (igual que el bug real).
set_user_context("test_local", "Angel", imagen_path=None, es_voz=False, continua_sesion=True)

state = {"messages": HISTORIAL + [HumanMessage(content=PREGUNTA)]}
print(f"→ Pregunta del turno actual (sin foto): {PREGUNTA!r}\n")
resp = graph.invoke(state)["messages"][-1].content
if isinstance(resp, list):
    resp = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in resp)

print("=== RESPUESTA DEL BOT ===")
print(resp)
print("=========================\n")

# Heurística de alucinación: frases de "registro" en un turno sin foto.
malas = [
    r"he procesado la imagen",
    r"se registr[oó] un nuevo gasto",
    r"\bCFE\b",
    r"registr[eé] (un|el) (nuevo )?gasto",
]
hits = [p for p in malas if re.search(p, resp, re.IGNORECASE)]
if hits:
    print(f"❌ POSIBLE ALUCINACIÓN — coincidió: {hits}")
    sys.exit(1)
else:
    print("✅ Sin frases de registro inventado. El bot respondió la pregunta, no narró un registro.")
