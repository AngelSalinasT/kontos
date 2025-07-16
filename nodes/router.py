# nodes/router.py
from typing import Dict, Any
from langchain_core.messages import HumanMessage
import re
from nodes.respuesta_general import respuesta_general_node
# Integrar memoria
from nodes.memory import get_user_state, clear_user_state

# Importar el LLM no es necesario aquí si se pasa como argumento
# from langchain_google_genai import GoogleGenerativeAI # No necesario si se pasa

def router_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo router que clasifica la intención del usuario y enruta a la acción/nodo correcto.
    Establece 'decision' en el estado.
    """
    user_id = state.get("user_id", "1234")
    user_input = state["messages"][-1].content.lower()

    # --- INTEGRACIÓN DE MEMORIA ---
    memory_state = get_user_state(user_id)
    if memory_state:
        # Si hay acción pendiente, enrutar directamente según la acción guardada
        pending_action = memory_state.get("pending_action")
        if pending_action == "eliminar_gasto":
            clear_user_state(user_id)
            return {**state, "decision": "eliminar_gasto", "parsed_data": {"id": user_input.strip()}}
        elif pending_action == "eliminar_gasto_fijo":
            clear_user_state(user_id)
            return {**state, "decision": "eliminar_gasto_fijo", "parsed_data": {"id": user_input.strip()}}
        elif pending_action == "eliminar_ingreso_fijo":
            clear_user_state(user_id)
            return {**state, "decision": "eliminar_ingreso_fijo", "parsed_data": {"id": user_input.strip()}}
        elif pending_action == "editar_gasto":
            clear_user_state(user_id)
            return {**state, "decision": "editar_gasto", "parsed_data": {"id": user_input.strip()}}
        elif pending_action == "editar_gasto_fijo":
            clear_user_state(user_id)
            return {**state, "decision": "editar_gasto_fijo", "parsed_data": {"id": user_input.strip()}}
        elif pending_action == "editar_ingreso_fijo":
            clear_user_state(user_id)
            return {**state, "decision": "editar_ingreso_fijo", "parsed_data": {"id": user_input.strip()}}
        # Puedes agregar más acciones pendientes aquí
    # --- FIN INTEGRACIÓN DE MEMORIA ---

    # Reglas simples para eficiencia
    if any(k in user_input for k in ["total", "reporte", "cuánto", "suma", "gastado", "consultar"]):
        decision = "parse_total"
    elif any(k in user_input for k in ["listar gastos fijos", "ver gastos fijos", "muestra gastos fijos"]):
        decision = "listar_gastos_fijos"
    elif any(k in user_input for k in ["listar ingresos fijos", "ver ingresos fijos", "muestra ingresos fijos"]):
        decision = "listar_ingresos_fijos"
    elif any(k in user_input for k in ["listar gastos", "ver gastos", "muestra gastos"]):
        decision = "parse_listar_gastos"
    elif any(k in user_input for k in ["eliminar gasto fijo", "borrar gasto fijo", "quitar gasto fijo"]):
        decision = "parse_eliminar_gasto_fijo"
    elif any(k in user_input for k in ["eliminar ingreso fijo", "borrar ingreso fijo", "quitar ingreso fijo"]):
        decision = "parse_eliminar_ingreso_fijo"
    elif any(k in user_input for k in ["eliminar gasto", "borrar gasto", "quitar gasto"]):
        decision = "parse_eliminar_gasto"
    elif any(k in user_input for k in ["editar gasto fijo", "modifica gasto fijo", "cambia gasto fijo"]):
        decision = "parse_editar_gasto_fijo"
    elif any(k in user_input for k in ["editar ingreso fijo", "modifica ingreso fijo", "cambia ingreso fijo"]):
        decision = "parse_editar_ingreso_fijo"
    elif any(k in user_input for k in ["editar gasto", "modifica gasto", "cambia gasto"]):
        decision = "parse_editar_gasto"
    elif any(k in user_input for k in ["gasto fijo", "pago fijo", "recurrente"]):
        decision = "parse_gastos_fijos"
    elif any(k in user_input for k in ["ingreso fijo", "sueldo fijo", "ingreso recurrente"]):
        decision = "parse_ingresos_fijos"
    elif any(k in user_input for k in ["gasté", "compré", "pagué", "$", "pesos", "euros", "dólares"]):
        decision = "parse_movement"
    elif any(k in user_input for k in ["respuesta general", "responder", "explicar", "ayuda"]):
        decision = "respuesta_general"
    else:
        # Usar LLM como fallback para casos ambiguos
        prompt = f"""
Clasifica el siguiente mensaje del usuario: "{user_input}"

Responde SOLO con una de las siguientes palabras:
- "parse_movement" para registrar gasto normal
- "parse_gastos_fijos" para registrar gasto fijo
- "parse_ingresos_fijos" para registrar ingreso fijo
- "parse_listar_gastos" para listar gastos normales
- "listar_gastos_fijos" para listar gastos fijos
- "listar_ingresos_fijos" para listar ingresos fijos
- "parse_editar_gasto" para editar gasto normal
- "parse_editar_gasto_fijo" para editar gasto fijo
- "parse_editar_ingreso_fijo" para editar ingreso fijo
- "parse_eliminar_gasto" para eliminar gasto normal
- "parse_eliminar_gasto_fijo" para eliminar gasto fijo
- "parse_eliminar_ingreso_fijo" para eliminar ingreso fijo
- "parse_total" para consultar totales o reportes
- "respuesta_general" para solicitar una respuesta general

Respuesta:"""
        llm_response = llm.invoke(prompt).strip().upper()
        # Normalizar a minúsculas para que coincida con las claves del grafo
        decision = llm_response.lower() if llm_response.lower() in [
            "parse_movement", "parse_gastos_fijos", "parse_ingresos_fijos",
            "parse_listar_gastos", "listar_gastos_fijos", "listar_ingresos_fijos",
            "parse_editar_gasto", "parse_editar_gasto_fijo", "parse_editar_ingreso_fijo",
            "parse_eliminar_gasto", "parse_eliminar_gasto_fijo", "parse_eliminar_ingreso_fijo",
            "parse_total", "respuesta_general"
        ] else "parse_movement"

    print(f"📌 Router Node Decisión: {decision}")
    return {
        **state,
        "decision": decision
    }
