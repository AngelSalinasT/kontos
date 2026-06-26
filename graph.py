"""Ensamble del grafo de Kontos.

    START ─dispatch(por tipo)─┬─ texto ──────────┐
                             ├─ transcribir ─────┤→ agente ⇄ tools → END
                             └─ extraer_imagen ──┘

Las tres ramas de entrada son deterministas: dejan el turno como TEXTO listo para
el agente. El agente (ReAct) decide qué herramientas usar; no procesa medios.
"""
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
from state import State
from nodes.dispatch import route_por_tipo
from nodes.texto import texto_node
from nodes.transcribir import transcribir_node
from nodes.extraer_imagen import extraer_imagen_node
from nodes.agente import agente_node

load_dotenv()


def build_graph():
    g = StateGraph(State)
    g.add_node("texto", texto_node)
    g.add_node("transcribir", transcribir_node)
    g.add_node("extraer_imagen", extraer_imagen_node)
    g.add_node("agente", agente_node)

    g.add_conditional_edges(START, route_por_tipo, {
        "texto": "texto",
        "transcribir": "transcribir",
        "extraer_imagen": "extraer_imagen",
    })
    g.add_edge("texto", "agente")
    g.add_edge("transcribir", "agente")
    g.add_edge("extraer_imagen", "agente")
    g.add_edge("agente", END)
    return g.compile()


graph = build_graph()
