def respuesta_general_node(state, llm=None):
    """
    Nodo que responde a dudas generales sobre Kontos o su propósito, usando plantillas para saludos y funciones frecuentes. Si no coincide, usa el LLM.
    """
    user_input = state["messages"][-1].content.lower().strip() if "messages" in state and state["messages"] else ""
    # Plantillas para saludos
    saludos = ["hola", "buenos días", "buenas tardes", "buenas noches", "hey", "hello", "holi", "saludos"]
    if user_input in saludos:
        respuesta = "¡Hola! Soy Kontos, tu asistente financiero. ¿En qué puedo ayudarte hoy?"
    # Plantillas para funciones frecuentes
    elif ("registrar" in user_input or "agregar" in user_input or "añadir" in user_input) and "gasto" in user_input:
        respuesta = "Para registrar un gasto, dime el concepto, el monto y la fecha. Ejemplo: ‘15 julio Uber Eats $250’."
    elif ("registrar" in user_input or "agregar" in user_input or "añadir" in user_input) and ("ingreso fijo" in user_input or "gasto fijo" in user_input):
        respuesta = "Para registrar un gasto o ingreso fijo, dime el concepto, monto y periodicidad. Ejemplo: ‘Registrar ingreso fijo sueldo $10,000 mensual’."
    elif "editar" in user_input and "gasto fijo" in user_input:
        respuesta = "Para editar un gasto fijo, dime el ID o el concepto y el nuevo valor. Ejemplo: ‘Edita el gasto fijo 5 a $800’."
    elif "editar" in user_input and "ingreso fijo" in user_input:
        respuesta = "Para editar un ingreso fijo, dime el ID o el concepto y el nuevo valor. Ejemplo: ‘Edita el ingreso fijo 3 a $12,000’."
    elif "editar" in user_input and "gasto" in user_input:
        respuesta = "Para editar un gasto, dime el ID o el concepto y el nuevo valor. Ejemplo: ‘Edita el gasto 12 a $300’."
    elif "eliminar" in user_input and "gasto fijo" in user_input:
        respuesta = "Para eliminar un gasto fijo, dime el ID o el concepto. Ejemplo: ‘Elimina el gasto fijo 7’."
    elif "eliminar" in user_input and "ingreso fijo" in user_input:
        respuesta = "Para eliminar un ingreso fijo, dime el ID o el concepto. Ejemplo: ‘Elimina el ingreso fijo 2’."
    elif "eliminar" in user_input and "gasto" in user_input:
        respuesta = "Para eliminar un gasto, dime el ID o el concepto. Ejemplo: ‘Elimina el gasto 15’."
    elif ("listar" in user_input or "ver" in user_input or "mostrar" in user_input) and "gasto fijo" in user_input:
        respuesta = "Puedes pedirme ‘Listar gastos fijos’ y te mostraré el detalle de tus gastos fijos registrados."
    elif ("listar" in user_input or "ver" in user_input or "mostrar" in user_input) and "ingreso fijo" in user_input:
        respuesta = "Puedes pedirme ‘Listar ingresos fijos’ y te mostraré el detalle de tus ingresos fijos registrados."
    elif ("listar" in user_input or "ver" in user_input or "mostrar" in user_input) and "gasto" in user_input:
        respuesta = "Puedes pedirme ‘Listar gastos de julio’ o ‘Ver mis gastos’. Te mostraré el detalle por periodo o categoría."
    elif "total" in user_input or "reporte" in user_input or "cuánto" in user_input or "gastado" in user_input or "consultar" in user_input:
        respuesta = "Solo pregunta ‘¿Cuánto he gastado este mes?’ o ‘Dame un reporte de mis gastos’. Te mostraré el resumen y observaciones."
    # Fallback: si no coincide con ninguna plantilla, usa el LLM
    else:
        if llm:
            prompt = f"""
Eres Kontos, un asistente financiero personal. Explica de forma clara y amigable cómo funciona Kontos y cómo puede ayudar al usuario según la siguiente pregunta o comentario:

Usuario: {user_input}

---

Características de Kontos:
- Registrar gastos normales, gastos fijos e ingresos fijos.
- Listar, editar y eliminar cualquier gasto o ingreso.
- Consultar totales y reportes por periodo y categoría.
- Asignar categorías a los movimientos.
- Advertir sobre presupuestos y dar observaciones financieras.
- Todo se gestiona de forma conversacional, guiando al usuario paso a paso.

Responde SOLO sobre funcionalidades de Kontos. Si la pregunta no tiene relación, indícalo amablemente.

Respuesta:
"""
            respuesta = llm.invoke(prompt).strip()
        else:
            respuesta = "🤖 Kontos es un asistente para llevar un registro financiero personal. Si tienes dudas sobre cómo usarlo, solo pregunta."
    return {**state, "final_response": respuesta} 