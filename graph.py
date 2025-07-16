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
from nodes.gastos_fijos import (
    parse_gastos_fijos_node, save_gastos_fijos_node, listar_gastos_fijos_node,
    parse_editar_gasto_fijo_node, editar_gasto_fijo_node,
    parse_eliminar_gasto_fijo_node, eliminar_gasto_fijo_node
)
from nodes.ingresos_fijos import (
    parse_ingresos_fijos_node, save_ingresos_fijos_node, listar_ingresos_fijos_node,
    parse_editar_ingreso_fijo_node, editar_ingreso_fijo_node,
    parse_eliminar_ingreso_fijo_node, eliminar_ingreso_fijo_node
)
from nodes.respuesta_general import respuesta_general_node
from nodes.gastos import (
    parse_listar_gastos_node, listar_gastos_node,
    parse_editar_gasto_node, editar_gasto_node,
    parse_eliminar_gasto_node, eliminar_gasto_node
)

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
    username: Optional[str] # Nombre de usuario de Telegram, opcional para pruebas

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

# Agregar nodos CRUD y generales
builder.add_node("parse_gastos_fijos", lambda state: parse_gastos_fijos_node(state, llm))
builder.add_node("save_gastos_fijos", save_gastos_fijos_node)
builder.add_node("listar_gastos_fijos", listar_gastos_fijos_node)
builder.add_node("parse_editar_gasto_fijo", lambda state: parse_editar_gasto_fijo_node(state, llm))
builder.add_node("editar_gasto_fijo", editar_gasto_fijo_node)
builder.add_node("parse_eliminar_gasto_fijo", lambda state: parse_eliminar_gasto_fijo_node(state, llm))
builder.add_node("eliminar_gasto_fijo", eliminar_gasto_fijo_node)

builder.add_node("parse_ingresos_fijos", lambda state: parse_ingresos_fijos_node(state, llm))
builder.add_node("save_ingresos_fijos", save_ingresos_fijos_node)
builder.add_node("listar_ingresos_fijos", listar_ingresos_fijos_node)
builder.add_node("parse_editar_ingreso_fijo", lambda state: parse_editar_ingreso_fijo_node(state, llm))
builder.add_node("editar_ingreso_fijo", editar_ingreso_fijo_node)
builder.add_node("parse_eliminar_ingreso_fijo", lambda state: parse_eliminar_ingreso_fijo_node(state, llm))
builder.add_node("eliminar_ingreso_fijo", eliminar_ingreso_fijo_node)

builder.add_node("parse_listar_gastos", lambda state: parse_listar_gastos_node(state, llm))
builder.add_node("listar_gastos", listar_gastos_node)
builder.add_node("parse_editar_gasto", lambda state: parse_editar_gasto_node(state, llm))
builder.add_node("editar_gasto", editar_gasto_node)
builder.add_node("parse_eliminar_gasto", lambda state: parse_eliminar_gasto_node(state, llm))
builder.add_node("eliminar_gasto", eliminar_gasto_node)

builder.add_node("respuesta_general", lambda state: respuesta_general_node(state, llm))

# Configurar el punto de entrada del grafo
builder.set_entry_point("router")

# Definir las aristas condicionales desde el nodo 'router'
builder.add_conditional_edges(
    "router",
    route_decision, # La función que determina el siguiente nodo
    {
        "parse_movement": "parse_movement", # Si route_decision devuelve "parse_movement", ir a ese nodo
        "parse_total": "parse_total",       # Si route_decision devuelve "parse_total", ir a ese nodo
        "parse_gastos_fijos": "parse_gastos_fijos",
        "listar_gastos_fijos": "listar_gastos_fijos",
        "parse_editar_gasto_fijo": "parse_editar_gasto_fijo",
        "editar_gasto_fijo": "editar_gasto_fijo",
        "parse_eliminar_gasto_fijo": "parse_eliminar_gasto_fijo",
        "eliminar_gasto_fijo": "eliminar_gasto_fijo",
        "parse_ingresos_fijos": "parse_ingresos_fijos",
        "listar_ingresos_fijos": "listar_ingresos_fijos",
        "parse_editar_ingreso_fijo": "parse_editar_ingreso_fijo",
        "editar_ingreso_fijo": "editar_ingreso_fijo",
        "parse_eliminar_ingreso_fijo": "parse_eliminar_ingreso_fijo",
        "eliminar_ingreso_fijo": "eliminar_ingreso_fijo",
        "parse_listar_gastos": "parse_listar_gastos",
        "listar_gastos": "listar_gastos",
        "parse_editar_gasto": "parse_editar_gasto",
        "editar_gasto": "editar_gasto",
        "parse_eliminar_gasto": "parse_eliminar_gasto",
        "eliminar_gasto": "eliminar_gasto",
        "respuesta_general": "respuesta_general"
    }
)

# Definir las aristas directas
builder.add_edge("parse_movement", "save_to_db")
builder.add_edge("save_to_db", END) # Fin del grafo después de guardar
builder.add_edge("parse_total", "consultar_total")
builder.add_edge("consultar_total", END) # Fin del grafo después de consultar

# Definir las aristas directas para los nuevos flujos
builder.add_edge("parse_gastos_fijos", "save_gastos_fijos")
builder.add_edge("save_gastos_fijos", END)
builder.add_edge("parse_ingresos_fijos", "save_ingresos_fijos")
builder.add_edge("save_ingresos_fijos", END)
builder.add_edge("parse_listar_gastos", "listar_gastos")
builder.add_edge("listar_gastos", END)
builder.add_edge("parse_editar_gasto", "editar_gasto")
builder.add_edge("editar_gasto", END)
builder.add_edge("parse_eliminar_gasto", "eliminar_gasto")
builder.add_edge("eliminar_gasto", END)
builder.add_edge("parse_editar_gasto_fijo", "editar_gasto_fijo")
builder.add_edge("editar_gasto_fijo", END)
builder.add_edge("parse_eliminar_gasto_fijo", "eliminar_gasto_fijo")
builder.add_edge("eliminar_gasto_fijo", END)
builder.add_edge("parse_editar_ingreso_fijo", "editar_ingreso_fijo")
builder.add_edge("editar_ingreso_fijo", END)
builder.add_edge("parse_eliminar_ingreso_fijo", "eliminar_ingreso_fijo")
builder.add_edge("eliminar_ingreso_fijo", END)
builder.add_edge("listar_gastos_fijos", END)
builder.add_edge("listar_ingresos_fijos", END)
builder.add_edge("respuesta_general", END)

# Compilar el grafo
graph = builder.compile()

# Opcional: Visualizar el grafo (requiere graphviz)
# from IPython.display import Image, display
# display(Image(graph.get_graph().draw_png()))
