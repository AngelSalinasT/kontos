# graph.py - Orquestador del grafo con nodos modulares
import os
from dotenv import load_dotenv
from typing import Annotated, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_google_genai import GoogleGenerativeAI

# Importar las funciones de los nodos desde sus respectivos módulos
from nodes.router import router_node
from nodes.gastos import parse_movement_node, save_to_db_node
from nodes.total import parse_total_node, consultar_total_node

load_dotenv()
# Inicializar el LLM una sola vez aquí y pasarlo a los nodos si es necesario
llm = GoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY")
)

# ✅ DEFINICIÓN UNIFICADA DEL ESTADO DEL GRAFO
class State(TypedDict):
    messages: Annotated[list, add_messages] # Lista de mensajes del usuario
    decision: Optional[str] # Decisión del router, puede ser "parse_movement" o "parse_total"
    parsed_data: Optional[dict] # Datos parseados del movimiento o consulta
    final_response: Optional[str] # Respuesta final que se enviará al usuario
    user_id: Optional[str] # ID del usuario, opcional para pruebas

# Función de decisión para el router (se mantiene aquí para la lógica del grafo)
def route_decision(state: State) -> str:
    """Función de decisión para el router basada en el estado."""
    # El nodo router_node establecerá 'decision' en el estado
    return state.get("decision", "parse_movement") # Default a 'parse_movement' si no hay decisión

# ===== CONSTRUIR GRAFO =====

builder = StateGraph(State)

# Agregar nodos al constructor del grafo
# Pasamos el LLM a los nodos que lo necesitan
builder.add_node("router", lambda state: router_node(state, llm))
builder.add_node("parse_movement", lambda state: parse_movement_node(state, llm))
builder.add_node("save_to_db", save_to_db_node) # Este nodo no necesita LLM
builder.add_node("parse_total", lambda state: parse_total_node(state, llm))
builder.add_node("consultar_total", consultar_total_node) # Este nodo no necesita LLM

# Configurar el punto de entrada del grafo
builder.set_entry_point("router")

# Definir las aristas condicionales desde el nodo 'router'
builder.add_conditional_edges(
    "router",
    route_decision, # La función que determina el siguiente nodo
    {
        "parse_movement": "parse_movement", # Si route_decision devuelve "parse_movement", ir a ese nodo
        "parse_total": "parse_total"       # Si route_decision devuelve "parse_total", ir a ese nodo
    }
)

# Definir las aristas directas
builder.add_edge("parse_movement", "save_to_db")
builder.add_edge("save_to_db", END) # Fin del grafo después de guardar
builder.add_edge("parse_total", "consultar_total")
builder.add_edge("consultar_total", END) # Fin del grafo después de consultar

# Compilar el grafo
graph = builder.compile()

# Opcional: Visualizar el grafo (requiere graphviz)
# from IPython.display import Image, display
# display(Image(graph.get_graph().draw_png()))
