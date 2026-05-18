def respuesta_general_node(state, llm=None):
    """
    Responde a preguntas generales sobre Kontos.
    Usa plantillas para casos comunes; LLM como fallback.
    """
    user_input = state["messages"][-1].content.lower().strip() if state.get("messages") else ""

    saludos = {"hola", "buenos días", "buenas tardes", "buenas noches", "hey", "hello", "holi", "saludos"}
    if user_input in saludos:
        return {**state, "final_response": "¡Hola! Soy Kontos, tu asistente de finanzas y despensa. ¿En qué te ayudo?"}

    # Plantillas por tema
    plantillas = [
        # Finanzas — gastos
        (["registrar", "agregar", "añadir"], ["gasto"],
         "Para registrar un gasto escribe el concepto, monto y fecha. Ej: '15 julio Uber Eats $250'"),
        (["registrar", "agregar", "añadir"], ["gasto fijo", "pago fijo"],
         "Para un gasto fijo: 'gasto fijo renta $5000 mensual'. Te lo recordaré cada mes."),
        (["registrar", "agregar", "añadir"], ["ingreso fijo", "sueldo fijo"],
         "Para un ingreso fijo: 'ingreso fijo sueldo $25000 mensual'."),
        (["editar", "modificar", "cambiar"], ["gasto fijo"],
         "Para editar un gasto fijo: 'editar gasto fijo 5 a $800'."),
        (["editar", "modificar", "cambiar"], ["ingreso fijo"],
         "Para editar un ingreso fijo: 'editar ingreso fijo 3 a $12000'."),
        (["editar", "modificar", "cambiar"], ["gasto"],
         "Para editar un gasto: 'editar gasto 12 a $300'."),
        (["eliminar", "borrar", "quitar"], ["gasto fijo"],
         "Para eliminar un gasto fijo: 'eliminar gasto fijo 7'."),
        (["eliminar", "borrar", "quitar"], ["ingreso fijo"],
         "Para eliminar un ingreso fijo: 'eliminar ingreso fijo 2'."),
        (["eliminar", "borrar", "quitar"], ["gasto"],
         "Para eliminar un gasto: 'eliminar gasto 15'."),
        (["listar", "ver", "mostrar"], ["gasto fijo"],
         "Escribe 'listar gastos fijos' para ver todos tus gastos recurrentes."),
        (["listar", "ver", "mostrar"], ["ingreso fijo"],
         "Escribe 'listar ingresos fijos' para ver todos tus ingresos recurrentes."),
        (["listar", "ver", "mostrar"], ["gasto"],
         "Escribe 'ver gastos' o 'listar gastos de julio' para ver el detalle por periodo."),
        (["total", "reporte", "cuánto", "cuanto", "gastado", "consultar"], [],
         "Pregunta '¿Cuánto gasté este mes?' o 'Total de julio' para ver tu resumen."),
        # Presupuestos
        (["presupuesto"], [],
         "Puedo crear presupuestos por categoría: 'crear presupuesto comida $3000'.\n"
         "Para ver el avance: 'cómo voy'."),
        # Despensa
        (["despensa", "producto", "inventario"], [],
         "Gestiono tu despensa:\n"
         "• 'ver despensa' — lista con predicción de cuándo recomprar\n"
         "• 'agregar producto leche $428' — añadir al catálogo\n"
         "• 'compré leche Kirkland $428 en Costco' — registrar compra\n"
         "• 'lista de despensa' — qué comprar en el próximo viaje\n"
         "• 'cuándo compro el papel higiénico' — predicción por patrones"),
        (["compra", "costco", "ahorrera", "compré", "compre"], [],
         "Para registrar una compra de despensa: 'compré leche Kirkland $428 en Costco'."),
        (["lista", "comprar", "despensa"], [],
         "Escribe 'lista de despensa' y te digo qué necesitas comprar según tu historial."),
        (["ticket", "foto", "escanear", "ocr"], [],
         "Mándame una foto de tu ticket y lo proceso automáticamente para registrar tus compras."),
        (["voz", "audio", "hablar"], [],
         "Puedes enviarme notas de voz. Las transcribo y proceso igual que texto."),
    ]

    for verbos, sustantivos, respuesta in plantillas:
        match_verbo = not verbos or any(v in user_input for v in verbos)
        match_sust = not sustantivos or any(s in user_input for s in sustantivos)
        if match_verbo and match_sust:
            return {**state, "final_response": respuesta}

    # Pregunta de capacidades genérica
    if any(k in user_input for k in ["qué puedes", "que puedes", "ayuda", "help", "funciones", "capacidades"]):
        return {**state, "final_response": (
            "Soy Kontos, tu asistente de finanzas y despensa. Puedo:\n\n"
            "💰 *Finanzas*\n"
            "• Registrar gastos, ingresos y pagos fijos\n"
            "• Consultar totales por fecha o categoría\n"
            "• Gestionar presupuestos con % de avance\n\n"
            "🛒 *Despensa*\n"
            "• Administrar tu catálogo de productos del hogar\n"
            "• Registrar compras y calcular cuándo recomprar\n"
            "• Generar lista de compras inteligente\n"
            "• Escanear tickets con OCR\n\n"
            "🎙️ *Medios*\n"
            "• Notas de voz (se transcriben automáticamente)\n"
            "• Fotos de tickets (OCR automático)\n\n"
            "¿Qué quieres hacer?"
        )}

    # Fallback LLM
    if llm:
        prompt = f"""Eres Kontos, asistente de finanzas personales y despensa.
Responde brevemente a esta pregunta del usuario sobre cómo usar Kontos:

Usuario: {user_input}

Capacidades: registro de gastos, gastos/ingresos fijos, presupuestos por categoría,
gestión de despensa con predicción de resurtido, OCR de tickets, notas de voz.

Respuesta (máximo 3 líneas):"""
        return {**state, "final_response": llm.invoke(prompt).strip()}

    return {**state, "final_response": "Soy Kontos. Escribe 'ayuda' para ver qué puedo hacer."}
