import os
from dotenv import load_dotenv
from typing import Annotated, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI

# Nodos existentes
from nodes.router import router_node
from nodes.gastos import (
    parse_movement_node, save_to_db_node,
    parse_listar_gastos_node, listar_gastos_node,
    parse_editar_gasto_node, editar_gasto_node,
    parse_eliminar_gasto_node, eliminar_gasto_node,
)
from nodes.total import parse_total_node, consultar_total_node
from nodes.gastos_fijos import (
    parse_gastos_fijos_node, save_gastos_fijos_node, listar_gastos_fijos_node,
    parse_editar_gasto_fijo_node, editar_gasto_fijo_node,
    parse_eliminar_gasto_fijo_node, eliminar_gasto_fijo_node,
)
from nodes.ingresos_fijos import (
    parse_ingresos_fijos_node, save_ingresos_fijos_node, listar_ingresos_fijos_node,
    parse_editar_ingreso_fijo_node, editar_ingreso_fijo_node,
    parse_eliminar_ingreso_fijo_node, eliminar_ingreso_fijo_node,
)
from nodes.respuesta_general import respuesta_general_node

# Nodos nuevos
from nodes.presupuestos import (
    crear_presupuesto_node, ver_presupuesto_node,
    editar_presupuesto_node, eliminar_presupuesto_node,
)
from nodes.despensa.productos import (
    crear_producto_node, listar_productos_node,
    editar_producto_node, desactivar_producto_node,
)
from nodes.despensa.compras import (
    registrar_compra_node, listar_compras_node,
    editar_compra_node, eliminar_compra_node,
)
from nodes.despensa.lista import generar_lista_despensa_node, consultar_prediccion_node
from nodes.despensa.tickets import procesar_ticket_node, listar_tickets_node, eliminar_ticket_node

load_dotenv()


class _StrLLM:
    """Envuelve ChatGoogleGenerativeAI para que .invoke() devuelva str en vez de AIMessage."""
    def __init__(self, chat_llm):
        self._llm = chat_llm

    def invoke(self, prompt: str) -> str:
        result = self._llm.invoke(prompt)
        return result.content if hasattr(result, "content") else str(result)


llm = _StrLLM(ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0,
))


class State(TypedDict):
    messages: Annotated[list, add_messages]
    decision: Optional[str]
    parsed_data: Optional[dict]
    final_response: Optional[str]
    user_id: Optional[str]
    username: Optional[str]
    imagen_path: Optional[str]
    es_voz: Optional[bool]


def route_decision(state: State) -> str:
    return state.get("decision", "parse_movement")


def build_graph():
    builder = StateGraph(State)

    # ── Nodos existentes ──────────────────────────────────────────────────────
    builder.add_node("router",                      lambda s: router_node(s, llm))
    builder.add_node("parse_movement",              lambda s: parse_movement_node(s, llm))
    builder.add_node("save_to_db",                  save_to_db_node)
    builder.add_node("parse_total",                 lambda s: parse_total_node(s, llm))
    builder.add_node("consultar_total",             consultar_total_node)
    builder.add_node("parse_gastos_fijos",          lambda s: parse_gastos_fijos_node(s, llm))
    builder.add_node("save_gastos_fijos",           save_gastos_fijos_node)
    builder.add_node("listar_gastos_fijos",         listar_gastos_fijos_node)
    builder.add_node("parse_editar_gasto_fijo",     lambda s: parse_editar_gasto_fijo_node(s, llm))
    builder.add_node("editar_gasto_fijo",           editar_gasto_fijo_node)
    builder.add_node("parse_eliminar_gasto_fijo",   lambda s: parse_eliminar_gasto_fijo_node(s, llm))
    builder.add_node("eliminar_gasto_fijo",         eliminar_gasto_fijo_node)
    builder.add_node("parse_ingresos_fijos",        lambda s: parse_ingresos_fijos_node(s, llm))
    builder.add_node("save_ingresos_fijos",         save_ingresos_fijos_node)
    builder.add_node("listar_ingresos_fijos",       listar_ingresos_fijos_node)
    builder.add_node("parse_editar_ingreso_fijo",   lambda s: parse_editar_ingreso_fijo_node(s, llm))
    builder.add_node("editar_ingreso_fijo",         editar_ingreso_fijo_node)
    builder.add_node("parse_eliminar_ingreso_fijo", lambda s: parse_eliminar_ingreso_fijo_node(s, llm))
    builder.add_node("eliminar_ingreso_fijo",       eliminar_ingreso_fijo_node)
    builder.add_node("parse_listar_gastos",         lambda s: parse_listar_gastos_node(s, llm))
    builder.add_node("listar_gastos",               listar_gastos_node)
    builder.add_node("parse_editar_gasto",          lambda s: parse_editar_gasto_node(s, llm))
    builder.add_node("editar_gasto",                editar_gasto_node)
    builder.add_node("parse_eliminar_gasto",        lambda s: parse_eliminar_gasto_node(s, llm))
    builder.add_node("eliminar_gasto",              eliminar_gasto_node)
    builder.add_node("respuesta_general",           lambda s: respuesta_general_node(s, llm))

    # ── Nodos nuevos ──────────────────────────────────────────────────────────
    builder.add_node("crear_presupuesto",           lambda s: crear_presupuesto_node(s, llm))
    builder.add_node("ver_presupuesto",             ver_presupuesto_node)
    builder.add_node("editar_presupuesto",          lambda s: editar_presupuesto_node(s, llm))
    builder.add_node("eliminar_presupuesto",        lambda s: eliminar_presupuesto_node(s, llm))
    builder.add_node("crear_producto",              lambda s: crear_producto_node(s, llm))
    builder.add_node("listar_productos",            lambda s: listar_productos_node(s, llm))
    builder.add_node("editar_producto",             lambda s: editar_producto_node(s, llm))
    builder.add_node("desactivar_producto",         lambda s: desactivar_producto_node(s, llm))
    builder.add_node("registrar_compra",            lambda s: registrar_compra_node(s, llm))
    builder.add_node("listar_compras",              lambda s: listar_compras_node(s, llm))
    builder.add_node("editar_compra",               lambda s: editar_compra_node(s, llm))
    builder.add_node("eliminar_compra",             lambda s: eliminar_compra_node(s, llm))
    builder.add_node("generar_lista_despensa",      generar_lista_despensa_node)
    builder.add_node("consultar_prediccion",        lambda s: consultar_prediccion_node(s, llm))
    builder.add_node("procesar_ticket",             lambda s: procesar_ticket_node(s, llm))
    builder.add_node("listar_tickets",              listar_tickets_node)
    builder.add_node("eliminar_ticket",             lambda s: eliminar_ticket_node(s, llm))

    # ── Routing condicional desde router ─────────────────────────────────────
    builder.set_entry_point("router")
    builder.add_conditional_edges("router", route_decision, {
        "parse_movement":              "parse_movement",
        "parse_total":                 "parse_total",
        "parse_gastos_fijos":          "parse_gastos_fijos",
        "listar_gastos_fijos":         "listar_gastos_fijos",
        "parse_editar_gasto_fijo":     "parse_editar_gasto_fijo",
        "editar_gasto_fijo":           "editar_gasto_fijo",
        "parse_eliminar_gasto_fijo":   "parse_eliminar_gasto_fijo",
        "eliminar_gasto_fijo":         "eliminar_gasto_fijo",
        "parse_ingresos_fijos":        "parse_ingresos_fijos",
        "listar_ingresos_fijos":       "listar_ingresos_fijos",
        "parse_editar_ingreso_fijo":   "parse_editar_ingreso_fijo",
        "editar_ingreso_fijo":         "editar_ingreso_fijo",
        "parse_eliminar_ingreso_fijo": "parse_eliminar_ingreso_fijo",
        "eliminar_ingreso_fijo":       "eliminar_ingreso_fijo",
        "parse_listar_gastos":         "parse_listar_gastos",
        "listar_gastos":               "listar_gastos",
        "parse_editar_gasto":          "parse_editar_gasto",
        "editar_gasto":                "editar_gasto",
        "parse_eliminar_gasto":        "parse_eliminar_gasto",
        "eliminar_gasto":              "eliminar_gasto",
        "respuesta_general":           "respuesta_general",
        "crear_presupuesto":           "crear_presupuesto",
        "ver_presupuesto":             "ver_presupuesto",
        "editar_presupuesto":          "editar_presupuesto",
        "eliminar_presupuesto":        "eliminar_presupuesto",
        "crear_producto":              "crear_producto",
        "listar_productos":            "listar_productos",
        "editar_producto":             "editar_producto",
        "desactivar_producto":         "desactivar_producto",
        "registrar_compra":            "registrar_compra",
        "listar_compras":              "listar_compras",
        "editar_compra":               "editar_compra",
        "eliminar_compra":             "eliminar_compra",
        "generar_lista_despensa":      "generar_lista_despensa",
        "consultar_prediccion":        "consultar_prediccion",
        "procesar_ticket":             "procesar_ticket",
        "listar_tickets":              "listar_tickets",
        "eliminar_ticket":             "eliminar_ticket",
    })

    # ── Edges parse → acción → END ────────────────────────────────────────────
    builder.add_edge("parse_movement",              "save_to_db")
    builder.add_edge("parse_total",                 "consultar_total")
    builder.add_edge("parse_gastos_fijos",          "save_gastos_fijos")
    builder.add_edge("parse_editar_gasto_fijo",     "editar_gasto_fijo")
    builder.add_edge("parse_eliminar_gasto_fijo",   "eliminar_gasto_fijo")
    builder.add_edge("parse_ingresos_fijos",        "save_ingresos_fijos")
    builder.add_edge("parse_editar_ingreso_fijo",   "editar_ingreso_fijo")
    builder.add_edge("parse_eliminar_ingreso_fijo", "eliminar_ingreso_fijo")
    builder.add_edge("parse_listar_gastos",         "listar_gastos")
    builder.add_edge("parse_editar_gasto",          "editar_gasto")
    builder.add_edge("parse_eliminar_gasto",        "eliminar_gasto")

    for node in [
        "save_to_db", "consultar_total",
        "save_gastos_fijos", "listar_gastos_fijos", "editar_gasto_fijo", "eliminar_gasto_fijo",
        "save_ingresos_fijos", "listar_ingresos_fijos", "editar_ingreso_fijo", "eliminar_ingreso_fijo",
        "listar_gastos", "editar_gasto", "eliminar_gasto",
        "respuesta_general",
        "crear_presupuesto", "ver_presupuesto", "editar_presupuesto", "eliminar_presupuesto",
        "crear_producto", "listar_productos", "editar_producto", "desactivar_producto",
        "registrar_compra", "listar_compras", "editar_compra", "eliminar_compra",
        "generar_lista_despensa", "consultar_prediccion",
        "procesar_ticket", "listar_tickets", "eliminar_ticket",
    ]:
        builder.add_edge(node, END)

    return builder.compile()


graph = build_graph()
