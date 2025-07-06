# debug_tools.py - Herramientas para debugging

def debug_state(state, node_name="Unknown"):
    """Imprime el estado actual para debugging"""
    print(f"\n🔍 DEBUG - {node_name}")
    print(f"📝 Messages: {len(state.get('messages', []))}")
    print(f"🎯 Decision: {state.get('decision')}")
    print(f"📊 Parsed Data: {state.get('parsed_data')}")
    print(f"💬 Final Response: {state.get('final_response')}")
    print("-" * 50)

def test_llm_parsing():
    """Prueba el parsing del LLM con diferentes inputs"""
    test_cases = [
        "Gasté $50 en comida hoy",
        "Compré pan por 25 pesos",
        "Pagué 100 en gasolina ayer",
        "Cuánto gasté esta semana",
        "Total del mes"
    ]
    
    from langchain_google_genai import GoogleGenerativeAI
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    llm = GoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    
    for test in test_cases:
        print(f"\n🧪 Testing: {test}")
        
        # Test router
        router_prompt = f"""
Clasifica: "{test}"
Responde SOLO: "parse_movement" o "parse_total"
"""
        decision = llm.invoke(router_prompt)
        print(f"📌 Router: {decision}")
        
        # Test parsing
        if "movement" in decision.lower():
            parse_prompt = f"""
Extrae de: "{test}"
Responde SOLO JSON:
{{"fecha": "2025-01-20", "concepto": "X", "monto": 0.00}}
"""
            parsed = llm.invoke(parse_prompt)
            print(f"📊 Parsed: {parsed}")
        
        print("-" * 30)

def validate_json_structure(json_str):
    """Valida que el JSON tenga la estructura correcta"""
    import json
    
    try:
        data = json.loads(json_str)
        
        # Validar estructura de movimiento
        if "fecha" in data and "concepto" in data and "monto" in data:
            print("✅ Estructura de movimiento válida")
            return True
        
        # Validar estructura de consulta
        if "fecha_inicio" in data and "fecha_fin" in data:
            print("✅ Estructura de consulta válida")
            return True
        
        print("❌ Estructura JSON inválida")
        return False
        
    except json.JSONDecodeError:
        print("❌ JSON inválido")
        return False