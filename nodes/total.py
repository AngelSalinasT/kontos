# nodes/total.py
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from typing import Dict, Any, Optional
import json
import re
from datetime import datetime, timedelta

# Modelos Pydantic para la salida estructurada
class Periodo(BaseModel):
    fecha_inicio: str = Field(..., example="2023-07-01")
    fecha_fin: str = Field(..., example="2023-07-31")

# Función de utilidad para parsear JSON de forma robusta
def parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extrae JSON de forma más robusta."""
    try:
        text = text.strip()
        text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error in total.py: {e} in text: {text[:200]}...")
        return None
    except Exception as e:
        print(f"❌ General Error parsing JSON in total.py: {e} in text: {text[:200]}...")
        return None

def parse_total_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que parsea la solicitud de consulta de totales usando LLM.
    Establece 'parsed_data' o 'final_response' en caso de error.
    """
    user_input = state["messages"][-1].content
    
    today = datetime.today()
    
    prompt = f"""
Hoy es {today.strftime('%Y-%m-%d')}.
El usuario pregunta: "{user_input}"

Determina el rango de fechas que el usuario quiere consultar.
Si el usuario no especifica un rango claro, asume "este mes".

REGLAS PARA FECHAS:
- "este mes": Desde el primer día del mes actual hasta hoy.
- "mes pasado": Desde el primer día del mes anterior hasta el último día del mes anterior.
- "esta semana": Desde el lunes de la semana actual hasta hoy.
- "últimos X días": Desde hace X días hasta hoy.
- "julio": Desde el 1 de julio del año actual hasta el 31 de julio del año actual.
- "2023": Desde el 1 de enero de 2023 hasta el 31 de diciembre de 2023.

Responde SOLO con un objeto JSON que siga este esquema Pydantic:
{{
    "fecha_inicio": "YYYY-MM-DD",
    "fecha_fin": "YYYY-MM-DD"
}}

Ejemplo:
Input: "total de julio"
Output: {{
    "fecha_inicio": "{today.year}-07-01",
    "fecha_fin": "{today.year}-07-31"
}}

Input: "total de esta semana"
Output: {{
    "fecha_inicio": "2025-07-01", // Lunes de esta semana
    "fecha_fin": "2025-07-06" // Hoy
}}

Input: "{user_input}"
Output:"""
    
    try:
        response = llm.invoke(prompt) # Si ya es un string, no necesitamos .content
        print(f"🔍 Raw LLM response for parse_total_node: {response}")
        
        parsed_data = parse_json_from_text(response)
        
        if not parsed_data:
            # Fallback: Si el LLM no puede parsear, por defecto este mes
            first_day_of_month = today.replace(day=1)
            parsed_data = {
                "fecha_inicio": first_day_of_month.strftime('%Y-%m-%d'),
                "fecha_fin": today.strftime('%Y-%m-%d')
            }
            print(f"⚠️ Fallback a 'este mes' para consulta de total: {parsed_data}")
        
        # Validar formato de fechas usando Pydantic
        try:
            periodo = Periodo(**parsed_data)
            # Asegurarse de que las fechas sean válidas y en el orden correcto
            if datetime.strptime(periodo.fecha_inicio, '%Y-%m-%d') > datetime.strptime(periodo.fecha_fin, '%Y-%m-%d'):
                raise ValueError("Fecha de inicio no puede ser posterior a fecha fin.")
            return {
                **state,
                "parsed_data": periodo.dict()
            }
        except Exception as e:
            # Si las fechas no son válidas o el modelo falla, usar fallback
            first_day_of_month = today.replace(day=1)
            parsed_data = {
                "fecha_inicio": first_day_of_month.strftime('%Y-%m-%d'),
                "fecha_fin": today.strftime('%Y-%m-%d')
            }
            print(f"⚠️ Fechas inválidas o error de Pydantic ({e}), fallback a 'este mes': {parsed_data}")
            return {
                **state,
                "parsed_data": parsed_data,
                "final_response": f"❌ No pude entender el período. Asumiendo 'este mes'. Error: {e}"
            }
        
    except Exception as e:
        print(f"❌ Error en parse_total_node: {e}")
        return {
            **state,
            "parsed_data": None,
            "final_response": "❌ Error interno al procesar la consulta de total. Por favor, intenta de nuevo."
        }

def consultar_total_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que consulta el total de gastos en el período especificado.
    Establece 'final_response'.
    """

    from tools import consultar_total_quincenal_tool
        
    data = state["parsed_data"]

    if not state.get("parsed_data"):
        return {
            **state,
            "final_response": "❌ No hay información de fechas válida para consultar."
        }
    
    try:
        from tools import consultar_total_quincenal_tool # Importar aquí para evitar circular
        
        data = state["parsed_data"]
        
        current_user_id = state.get("user_id", "default_user") # Obtener del estado

        total = consultar_total_quincenal_tool(
            user_id=current_user_id, # Usar el user_id
            fecha_inicio=data["fecha_inicio"],
            fecha_fin=data["fecha_fin"]
        )
        
        # Asegurarse de que el total sea un flotante y formatearlo
        total_float = float(total) if isinstance(total, (str, int)) else total
        
        response = (
            f"💰 Total de gastos:\n"
            f"📅 Del {data['fecha_inicio']} al {data['fecha_fin']}\n"
            f"💵 ${total_float:,.2f}"
        )
        
        return {
            **state,
            "final_response": response
        }
        
    except Exception as e:
        print(f"❌ Error al consultar total en DB en consultar_total_node: {e}")
        return {
            **state,
            "final_response": "❌ Error al consultar el total de gastos. Por favor, intenta de nuevo."
        }
