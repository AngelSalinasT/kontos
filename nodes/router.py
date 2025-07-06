# nodes/router.py
from typing import Dict, Any
from langchain_core.messages import HumanMessage
import re

# Importar el LLM no es necesario aquí si se pasa como argumento
# from langchain_google_genai import GoogleGenerativeAI # No necesario si se pasa

def router_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo router que clasifica la intención del usuario.
    Establece 'decision' en el estado.
    """
    user_input = state["messages"][-1].content.lower()
    
    # Reglas simples primero para eficiencia
    if any(keyword in user_input for keyword in ["total", "cuánto", "suma", "gastado", "consultar"]):
        decision = "parse_total"
    elif any(keyword in user_input for keyword in ["gasté", "compré", "pagué", "$", "pesos", "euros", "dólares"]):
        decision = "parse_movement"
    else:
        # Usar LLM solo como fallback para casos ambiguos
        prompt = f"""
Clasifica el siguiente mensaje del usuario: "{user_input}"

Responde SOLO con una de las siguientes palabras:
- "GASTO" si el mensaje describe un gasto o compra.
- "TOTAL" si el mensaje es una consulta sobre el total de gastos en un período.

Ejemplos:
Usuario: "Compré pan por $20" -> GASTO
Usuario: "Gasté 50 en gasolina" -> GASTO
Usuario: "Cuánto gasté en julio" -> TOTAL
Usuario: "Total de esta semana" -> TOTAL
Usuario: "Hola" -> GASTO (por defecto si no es claro)

Respuesta:"""
        
        llm_response = llm.invoke(prompt).content.strip().upper()
        decision = "parse_movement" if "GASTO" in llm_response else "parse_total"
    
    print(f"📌 Router Node Decisión: {decision}")
    
    # El router solo actualiza la 'decision' en el estado
    return {
        **state,
        "decision": decision
    }
