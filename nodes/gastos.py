# nodes/gastos.py
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime

# Modelos Pydantic para la salida estructurada
class Movimiento(BaseModel):
    fecha: str = Field(..., example="05 Julio")
    concepto: str = Field(..., example="Soriana")
    monto: float = Field(..., gt=0, example=385.30)

# Función de utilidad para parsear JSON de forma robusta
def parse_json_from_text(text: str) -> Optional[Any]: # Cambiado a Any porque puede ser lista o dict
    """Extrae JSON de forma más robusta."""
    try:
        text = text.strip()
        text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
        
        # Intentar parsear como lista primero, luego como objeto
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Si no es una lista, buscar un objeto JSON
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            
        return None # Si no se pudo parsear ni como lista ni como objeto
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error in gastos.py: {e} in text: {text[:200]}...")
        return None
    except Exception as e:
        print(f"❌ General Error parsing JSON in gastos.py: {e} in text: {text[:200]}...")
        return None

def parse_movement_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que parsea la información de uno o varios gastos específicos usando LLM.
    Establece 'parsed_data' (lista de dicts) o 'final_response' en caso de error.
    """
    user_input = state["messages"][-1].content
    
    # Prompt mejorado para solicitar una lista de JSONs si hay múltiples movimientos
    prompt = f"""
Extrae la información de los gastos del siguiente texto. Si hay múltiples gastos, devuélvelos como una lista de objetos JSON.

REGLAS:
1. La fecha debe ser en formato "DD Mes" (ej. "05 Julio"). Si no se especifica, usa la fecha actual (ej. "{datetime.now().strftime('%d %B')}").
2. El concepto debe ser una descripción concisa del gasto.
3. El monto debe ser un número flotante positivo.

Responde SOLO con un objeto JSON o una lista de objetos JSON que sigan este esquema Pydantic para cada movimiento:
{{
    "fecha": "string", // Formato "DD Mes"
    "concepto": "string",
    "monto": float // Mayor que 0
}}

Ejemplo válido para un solo movimiento:
Input: "15 Julio Supermercado $350.50"
Output: {{
    "fecha": "15 Julio",
    "concepto": "Supermercado",
    "monto": 350.50
}}

Ejemplo válido para múltiples movimientos:
Input: "05 Julio Soriana $385.30. 04 Julio Estaciones de ser $710.44"
Output: [
  {{
    "fecha": "05 Julio",
    "concepto": "Soriana",
    "monto": 385.30
  }},
  {{
    "fecha": "04 Julio",
    "concepto": "Estaciones de ser",
    "monto": 710.44
  }}
]

Input: "{user_input}"
Output:"""
    
    try:
        response = llm.invoke(prompt) # Ya no usamos .content aquí
        print(f"🔍 Raw LLM response for parse_movement_node: {response}")
        
        raw_parsed_data = parse_json_from_text(response)
        
        if not raw_parsed_data:
            return {
                **state,
                "parsed_data": None,
                "final_response": "❌ No pude entender la información del gasto. Intenta con formato: '15 Julio Supermercado $350.50' o lista de ellos."
            }
        
        # Asegurarse de que raw_parsed_data sea una lista
        if not isinstance(raw_parsed_data, list):
            raw_parsed_data = [raw_parsed_data] # Convertir a lista si es un solo objeto
            
        valid_movements = []
        errors = []
        for item in raw_parsed_data:
            try:
                movimiento = Movimiento(**item)
                valid_movements.append(movimiento.dict())
            except ValidationError as e:
                errors.append(f"Error en un movimiento: {e.errors()}")
            except Exception as e:
                errors.append(f"Error inesperado al validar un movimiento: {e}")

        if not valid_movements:
            return {
                **state,
                "parsed_data": None,
                "final_response": f"❌ No se pudo validar ningún movimiento. Errores: {'; '.join(errors) if errors else 'Desconocido'}"
            }
        
        return {
            **state,
            "parsed_data": valid_movements # Almacenar la lista de movimientos válidos
        }
        
    except Exception as e:
        print(f"❌ Error en parse_movement_node: {e}")
        return {
            **state,
            "parsed_data": None,
            "final_response": "❌ Error interno al procesar el gasto. Por favor, intenta de nuevo."
        }

def save_to_db_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que guarda uno o varios movimientos parseados en la base de datos.
    Establece 'final_response'.
    """
    # === ESTA LÍNEA ES LA CLAVE QUE FALTABA O ESTABA MAL ===
    parsed_movements = state.get("parsed_data") 
    
    if not parsed_movements or not isinstance(parsed_movements, list):
        return {
            **state,
            "final_response": "❌ No hay datos válidos (lista de movimientos) para guardar."
        }
    
    try:
        from tools import insertar_movimiento_tool
        
        saved_count = 0
        response_messages = []
        
        current_user_id = state.get("user_id", "1234") # Obtener user_id del estado
        current_username = state.get("username", "Desconocido") # Obtener username del estado
        
        for data in parsed_movements: # <-- Aquí se usa 'parsed_movements'
            # Asegurarse de que la fecha tenga el año actual si no se especifica
            fecha_str = data["fecha"]
            # Intentar parsear "DD Mes" y añadir el año actual
            try:
                fecha_obj = datetime.strptime(fecha_str, '%d %B')
                fecha_con_año = fecha_obj.replace(year=datetime.now().year).strftime('%d %B %Y')
            except ValueError:
                # Si no es "DD Mes", asumir que ya tiene el año o es un formato completo
                fecha_con_año = fecha_str
            
            insertar_movimiento_tool(
                user_id=current_user_id,
                username=current_username,
                fecha=fecha_con_año, # Esta fecha se convertirá a YYYY-MM-DD en db.py
                concepto=data["concepto"],
                monto=data["monto"],
                categoria="General",
                origen="Telegram"
            )
            saved_count += 1
            response_messages.append(f"✅ {data['concepto']} ${data['monto']:.2f}")
        
        final_response_text = f"✅ Se registraron {saved_count} gastos para {current_username}:\n" + "\n".join(response_messages)
        
        return {
            **state,
            "final_response": final_response_text
        }
        
    except Exception as e:
        print(f"❌ Error al guardar en DB en save_to_db_node: {e}")
        return {
            **state,
            "final_response": "❌ Error al guardar los gastos en la base de datos. Por favor, intenta de nuevo."
        }
