# test_graph.py - Script para probar el grafo
def test_graph_flow():
    """Prueba completa del flujo del grafo"""
    from graph import graph
    from langchain_core.messages import HumanMessage
    
    test_cases = [
        "Gasté $50 en almuerzo",
        "Compré café por 15 pesos",
        "Cuánto gasté esta semana",
        "Total del mes"
    ]
    
    for test in test_cases:
        print(f"\n🧪 Probando: {test}")
        
        try:
            result = graph.invoke({
                "messages": [HumanMessage(content=test)],
                "decision": None,
                "parsed_data": None,
                "final_response": None
            })
            
            print(f"✅ Resultado: {result.get('final_response')}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 40)

if __name__ == "__main__":
    print("🔧 Herramientas de Debug para LangGraph")
    print("1. test_llm_parsing() - Prueba el parsing del LLM")
    print("2. test_graph_flow() - Prueba el flujo completo")
    print("3. validate_json_structure() - Valida estructura JSON")
    
    # Ejecutar pruebas
    # test_llm_parsing()
    # test_graph_flow()