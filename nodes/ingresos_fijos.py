from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime
import sqlite3
from nodes.memory import set_user_state

# Modelo para ingreso fijo
class IngresoFijo(BaseModel):
    concepto: str = Field(..., example="Sueldo")
    monto: float = Field(..., gt=0, example=10000.0)
    categoria: str = Field("General", example="Salario")
    periodicidad: str = Field(..., example="mensual")
    fecha_inicio: Optional[str] = Field(None, example="2024-07-01")

# Utilidad para parsear JSON robusto
def parse_json_from_text(text: str) -> Optional[Any]:
    try:
        text = text.strip()
        text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        return None
    except Exception as e:
        print(f"❌ Error parsing JSON in ingresos_fijos.py: {e} in text: {text[:200]}...")
        return None

def parse_ingresos_fijos_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que parsea uno o varios ingresos fijos desde el mensaje del usuario usando LLM.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
Extrae la información de los ingresos fijos del siguiente texto. Si hay varios, devuélvelos como una lista de objetos JSON.

REGLAS:
1. El concepto debe ser una descripción concisa del ingreso fijo.
2. El monto debe ser un número flotante positivo.
3. La periodicidad debe ser un texto como "mensual", "quincenal", "semanal", etc.
4. Si el usuario menciona una categoría, inclúyela en el campo "categoria". Si no, usa "General".
5. Si el usuario menciona una fecha de inicio, inclúyela en el campo "fecha_inicio" (formato YYYY-MM-DD). Si no, usa la fecha actual.

Responde SOLO con un objeto JSON o una lista de objetos JSON que sigan este esquema:
{{
    "concepto": "string",
    "monto": float,
    "categoria": "string",
    "periodicidad": "string",
    "fecha_inicio": "YYYY-MM-DD" // opcional
}}

Ejemplo válido para un solo ingreso fijo:
Input: "Agrega un ingreso fijo de $10000 por sueldo cada mes"
Output: {{
    "concepto": "Sueldo",
    "monto": 10000.0,
    "categoria": "Salario",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
}}

Ejemplo válido para varios ingresos fijos:
Input: "Registrar renta $5000 mensual y freelance $2000 mensual"
Output: [
  {{
    "concepto": "Renta",
    "monto": 5000.0,
    "categoria": "Rentas",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
  }},
  {{
    "concepto": "Freelance",
    "monto": 2000.0,
    "categoria": "Servicios",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
  }}
]

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_ingresos_fijos_node: {response}")
        raw_parsed_data = parse_json_from_text(response)
        if not raw_parsed_data:
            return {
                **state,
                "parsed_data": None,
                "final_response": "❌ No pude entender la información de los ingresos fijos. Intenta con formato: 'Agrega un ingreso fijo de $10000 por sueldo cada mes' o lista de ellos."
            }
        if not isinstance(raw_parsed_data, list):
            raw_parsed_data = [raw_parsed_data]
        valid_ingresos = []
        errors = []
        for item in raw_parsed_data:
            try:
                ingreso = IngresoFijo(**item)
                valid_ingresos.append(ingreso.dict())
            except ValidationError as e:
                errors.append(f"Error en un ingreso fijo: {e.errors()}")
            except Exception as e:
                errors.append(f"Error inesperado al validar un ingreso fijo: {e}")
        if not valid_ingresos:
            return {
                **state,
                "parsed_data": None,
                "final_response": f"❌ No se pudo validar ningún ingreso fijo. Errores: {'; '.join(errors) if errors else 'Desconocido'}"
            }
        return {
            **state,
            "parsed_data": valid_ingresos
        }
    except Exception as e:
        print(f"❌ Error en parse_ingresos_fijos_node: {e}")
        return {
            **state,
            "parsed_data": None,
            "final_response": "❌ Error interno al procesar el ingreso fijo. Por favor, intenta de nuevo."
        }

def save_ingresos_fijos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que guarda uno o varios ingresos fijos parseados en la base de datos.
    Ahora verifica que el usuario exista en la tabla usuarios antes de registrar el ingreso fijo.
    """
    parsed_ingresos = state.get("parsed_data")
    if not parsed_ingresos or not isinstance(parsed_ingresos, list):
        return {
            **state,
            "final_response": "❌ No hay datos válidos (lista de ingresos fijos) para guardar."
        }
    try:
        saved_count = 0
        response_messages = []
        current_user_id = state.get("user_id", "1234")
        current_username = state.get("username", "Desconocido")
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        # Verificar o crear usuario
        cursor.execute("SELECT 1 FROM usuarios WHERE user_id = ?", (current_user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (user_id, username) VALUES (?, ?)", (current_user_id, current_username))
            conn.commit()
        for data in parsed_ingresos:
            categoria_nombre = data.get("categoria", "General").capitalize()
            # Buscar o crear la categoría
            cursor.execute("SELECT id FROM categorias WHERE nombre = ?", (categoria_nombre,))
            row = cursor.fetchone()
            if row:
                categoria_id = row[0]
            else:
                cursor.execute("INSERT INTO categorias (nombre, tipo) VALUES (?, 'ingreso')", (categoria_nombre,))
                categoria_id = cursor.lastrowid
                conn.commit()
            fecha_inicio = data.get("fecha_inicio") or datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                INSERT INTO ingresos_fijos (user_id, categoria_id, concepto, monto, fecha_inicio, periodicidad)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                current_user_id,
                categoria_id,
                data["concepto"],
                data["monto"],
                fecha_inicio,
                data["periodicidad"]
            ))
            saved_count += 1
            response_messages.append(f"✅ {data['concepto']} ${data['monto']:.2f} [{categoria_nombre}] cada {data['periodicidad']}")
        conn.commit()
        conn.close()
        final_response_text = f"✅ Se registraron {saved_count} ingresos fijos:\n" + "\n".join(response_messages)
        return {
            **state,
            "final_response": final_response_text
        }
    except Exception as e:
        print(f"❌ Error al guardar en DB en save_ingresos_fijos_node: {e}")
        return {
            **state,
            "final_response": "❌ Error al guardar los ingresos fijos en la base de datos. Por favor, intenta de nuevo."
        }

def listar_ingresos_fijos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que lista todos los ingresos fijos del usuario, mostrando ID, concepto, monto, categoría, periodicidad y fecha de inicio.
    """
    user_id = state.get("user_id", "1234")
    try:
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT inf.id, inf.concepto, inf.monto, c.nombre as categoria, inf.periodicidad, inf.fecha_inicio
            FROM ingresos_fijos inf
            LEFT JOIN categorias c ON inf.categoria_id = c.id
            WHERE inf.user_id = ?
            ORDER BY inf.fecha_inicio DESC, inf.id DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No hay ingresos fijos registrados."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "📋 Ingresos fijos registrados:\n" + "\n".join(lines)
        return {**state, "final_response": response}
    except Exception as e:
        print(f"❌ Error al listar ingresos fijos: {e}")
        return {**state, "final_response": "❌ Error al listar los ingresos fijos. Por favor, intenta de nuevo."}

def parse_editar_ingreso_fijo_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para editar un ingreso fijo.
    Extrae el ID y los campos a modificar. Si la información es ambigua, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere editar un ingreso fijo. Extrae el ID del ingreso fijo y los campos a modificar (concepto, monto, categoría, periodicidad, fecha_inicio).
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID y los nuevos valores, responde SOLO con un objeto JSON con los campos a modificar.

Ejemplo:
Input: "Cambia el monto del ingreso fijo 5 a 12000"
Output: {{"id": 5, "monto": 12000}}
Input: "Edita el ingreso fijo de renta a 6000"
Output: {{"busqueda": "renta"}}
Input: "Cambia la periodicidad del ingreso fijo 3 a quincenal"
Output: {{"id": 3, "periodicidad": "quincenal"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_editar_ingreso_fijo_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_editar_ingreso_fijo_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué ingreso fijo editar."}

def editar_ingreso_fijo_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que edita un ingreso fijo por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para editar el ingreso fijo."}
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT inf.id, inf.concepto, inf.monto, c.nombre as categoria, inf.periodicidad, inf.fecha_inicio
            FROM ingresos_fijos inf
            LEFT JOIN categorias c ON inf.categoria_id = c.id
            WHERE inf.user_id = ? AND (inf.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY inf.fecha_inicio DESC, inf.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron ingresos fijos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "Se encontraron varios ingresos fijos. Por favor, indica el ID a editar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para editar
        set_user_state(user_id, {"pending_action": "editar_ingreso_fijo"})
        return {**state, "final_response": response}
    # Si tiene ID y campos a modificar
    id_ingreso = data.get("id")
    if not id_ingreso:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del ingreso fijo a editar."}
    campos = []
    valores = []
    if "concepto" in data:
        campos.append("concepto = ?")
        valores.append(data["concepto"])
    if "monto" in data:
        campos.append("monto = ?")
        valores.append(data["monto"])
    if "periodicidad" in data:
        campos.append("periodicidad = ?")
        valores.append(data["periodicidad"])
    if "fecha_inicio" in data:
        campos.append("fecha_inicio = ?")
        valores.append(data["fecha_inicio"])
    if "categoria" in data:
        categoria_nombre = data["categoria"].capitalize()
        cursor.execute("SELECT id FROM categorias WHERE nombre = ?", (categoria_nombre,))
        row = cursor.fetchone()
        if row:
            categoria_id = row[0]
        else:
            cursor.execute("INSERT INTO categorias (nombre, tipo) VALUES (?, 'ingreso')", (categoria_nombre,))
            categoria_id = cursor.lastrowid
            conn.commit()
        campos.append("categoria_id = ?")
        valores.append(categoria_id)
    if not campos:
        conn.close()
        return {**state, "final_response": "❌ No se especificó ningún campo a modificar."}
    valores.append(id_ingreso)
    cursor.execute(f"UPDATE ingresos_fijos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", (*valores, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"✅ Ingreso fijo {id_ingreso} actualizado correctamente."}

def parse_eliminar_ingreso_fijo_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para eliminar un ingreso fijo.
    Extrae el ID o una búsqueda. Si es ambiguo, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere eliminar un ingreso fijo. Extrae el ID del ingreso fijo o una búsqueda por concepto/categoría.
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID, responde SOLO con un objeto JSON con "id": número.

Ejemplo:
Input: "Elimina el ingreso fijo 7"
Output: {{"id": 7}}
Input: "Elimina el ingreso fijo de renta"
Output: {{"busqueda": "renta"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_eliminar_ingreso_fijo_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_eliminar_ingreso_fijo_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué ingreso fijo eliminar."}

def eliminar_ingreso_fijo_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que elimina un ingreso fijo por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para eliminar el ingreso fijo."}
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT inf.id, inf.concepto, inf.monto, c.nombre as categoria, inf.periodicidad, inf.fecha_inicio
            FROM ingresos_fijos inf
            LEFT JOIN categorias c ON inf.categoria_id = c.id
            WHERE inf.user_id = ? AND (inf.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY inf.fecha_inicio DESC, inf.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron ingresos fijos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "Se encontraron varios ingresos fijos. Por favor, indica el ID a eliminar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para eliminar
        set_user_state(user_id, {"pending_action": "eliminar_ingreso_fijo"})
        return {**state, "final_response": response}
    # Si tiene ID
    id_ingreso = data.get("id")
    if not id_ingreso:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del ingreso fijo a eliminar."}
    cursor.execute("DELETE FROM ingresos_fijos WHERE id = ? AND user_id = ?", (id_ingreso, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"🗑️ Ingreso fijo {id_ingreso} eliminado correctamente."} 