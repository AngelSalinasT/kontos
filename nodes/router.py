from typing import Dict, Any
from nodes.memory import get_user_state, clear_user_state

VALID_DECISIONS = {
    # Existentes
    "parse_movement", "parse_total",
    "parse_gastos_fijos", "listar_gastos_fijos", "parse_editar_gasto_fijo",
    "editar_gasto_fijo", "parse_eliminar_gasto_fijo", "eliminar_gasto_fijo",
    "parse_ingresos_fijos", "listar_ingresos_fijos", "parse_editar_ingreso_fijo",
    "editar_ingreso_fijo", "parse_eliminar_ingreso_fijo", "eliminar_ingreso_fijo",
    "parse_listar_gastos", "listar_gastos", "parse_editar_gasto", "editar_gasto",
    "parse_eliminar_gasto", "eliminar_gasto", "respuesta_general",
    # Nuevos
    "crear_presupuesto", "ver_presupuesto", "editar_presupuesto", "eliminar_presupuesto",
    "crear_producto", "listar_productos", "editar_producto", "desactivar_producto",
    "registrar_compra", "listar_compras", "editar_compra", "eliminar_compra",
    "generar_lista_despensa", "consultar_prediccion",
    "procesar_ticket", "listar_tickets", "eliminar_ticket",
}

# Reglas por keyword — orden importa (más específico primero)
KEYWORD_RULES = [
    # Despensa — lista y predicción
    (["lista despensa", "lista de despensa", "qué compro", "que compro",
      "despensa de este mes", "qué necesito comprar", "hacer despensa"], "generar_lista_despensa"),
    (["cuándo compro", "cuando compro", "predicción", "prediccion",
      "próxima compra", "proxima compra", "cada cuánto", "cada cuanto"], "consultar_prediccion"),

    # Despensa — productos
    (["agregar producto", "agrega producto", "nuevo producto", "añadir producto",
      "añadir a despensa", "agrega a despensa"], "crear_producto"),
    (["ver despensa", "ver productos", "lista productos", "mis productos",
      "qué tengo en despensa", "que tengo en despensa"], "listar_productos"),
    (["editar producto", "modifica producto", "cambia producto", "actualiza producto"], "editar_producto"),
    (["quitar producto", "eliminar producto", "borrar producto",
      "desactivar producto", "sacar de despensa"], "desactivar_producto"),

    # Despensa — compras
    (["compré", "compre", "compré en costco", "compré en", "registrar compra despensa",
      "anotar compra"], "registrar_compra"),
    (["historial compras", "ver compras despensa", "mis compras",
      "compras del mes"], "listar_compras"),
    (["editar compra", "corregir compra", "modificar compra"], "editar_compra"),
    (["eliminar compra", "borrar compra", "quitar compra"], "eliminar_compra"),

    # Tickets OCR
    (["escanear ticket", "procesar ticket", "analizar ticket",
      "subir ticket", "foto del ticket"], "procesar_ticket"),
    (["ver tickets", "mis tickets", "tickets escaneados", "listar tickets"], "listar_tickets"),
    (["eliminar ticket", "borrar ticket"], "eliminar_ticket"),

    # Presupuestos
    (["crear presupuesto", "nuevo presupuesto", "agregar presupuesto",
      "presupuesto de"], "crear_presupuesto"),
    (["ver presupuesto", "mis presupuestos", "presupuesto actual",
      "cómo voy", "como voy"], "ver_presupuesto"),
    (["editar presupuesto", "cambiar presupuesto", "modificar presupuesto"], "editar_presupuesto"),
    (["eliminar presupuesto", "borrar presupuesto", "quitar presupuesto"], "eliminar_presupuesto"),

    # Financiero existente
    (["total", "reporte", "cuánto gasté", "cuanto gaste", "suma", "gastado", "consultar"], "parse_total"),
    (["listar gastos fijos", "ver gastos fijos", "muestra gastos fijos"], "listar_gastos_fijos"),
    (["listar ingresos fijos", "ver ingresos fijos", "muestra ingresos fijos"], "listar_ingresos_fijos"),
    (["listar gastos", "ver gastos", "muestra gastos"], "parse_listar_gastos"),
    (["eliminar gasto fijo", "borrar gasto fijo"], "parse_eliminar_gasto_fijo"),
    (["eliminar ingreso fijo", "borrar ingreso fijo"], "parse_eliminar_ingreso_fijo"),
    (["eliminar gasto", "borrar gasto"], "parse_eliminar_gasto"),
    (["editar gasto fijo", "modifica gasto fijo"], "parse_editar_gasto_fijo"),
    (["editar ingreso fijo", "modifica ingreso fijo"], "parse_editar_ingreso_fijo"),
    (["editar gasto", "modifica gasto", "cambia gasto"], "parse_editar_gasto"),
    (["gasto fijo", "pago fijo", "recurrente"], "parse_gastos_fijos"),
    (["ingreso fijo", "sueldo fijo", "ingreso recurrente"], "parse_ingresos_fijos"),
    (["gasté", "pagué", "$", "pesos"], "parse_movement"),
    (["ayuda", "help", "qué puedes hacer", "que puedes hacer"], "respuesta_general"),
]


def router_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_id = state.get("user_id", "1234")
    user_input = state["messages"][-1].content

    # Acciones pendientes en memoria (flujos de edición/eliminación con ID)
    memory_state = get_user_state(user_id)
    if memory_state:
        pending = memory_state.get("pending_action")
        if pending in VALID_DECISIONS:
            clear_user_state(user_id)
            return {**state, "decision": pending, "parsed_data": {"id": user_input.strip()}}

    lower = user_input.lower()

    # Reglas por keyword
    for keywords, decision in KEYWORD_RULES:
        if any(k in lower for k in keywords):
            print(f"📌 Router keyword → {decision}")
            return {**state, "decision": decision}

    # Fallback al LLM
    opciones = "\n".join(f'- "{d}"' for d in sorted(VALID_DECISIONS))
    prompt = f"""Clasifica el mensaje del usuario en UNA de estas opciones:
{opciones}

Responde SOLO con el nombre exacto de la opción.

Mensaje: "{user_input}"
Respuesta:"""

    llm_resp = llm.invoke(prompt).strip().lower().replace('"', '').replace("'", "")
    decision = llm_resp if llm_resp in VALID_DECISIONS else "parse_movement"
    print(f"📌 Router LLM → {decision}")
    return {**state, "decision": decision}
