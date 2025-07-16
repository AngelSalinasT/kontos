from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime
import sqlite3
from nodes.memory import set_user_state

# Modelo para gasto fijo
class GastoFijo(BaseModel):
    concepto: str = Field(..., example="Renta")
    monto: float = Field(..., gt=0, example=500.0)
    categoria: str = Field("General", example="Servicios")
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
        print(f"❌ Error parsing JSON in gastos_fijos.py: {e} in text: {text[:200]}...")
        return None

def parse_gastos_fijos_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que parsea uno o varios gastos fijos desde el mensaje del usuario usando LLM.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
Extrae la información de los gastos fijos del siguiente texto. Si hay varios, devuélvelos como una lista de objetos JSON.

REGLAS:
1. El concepto debe ser una descripción concisa del gasto fijo.
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

Ejemplo válido para un solo gasto fijo:
Input: "Agrega un gasto fijo de $500 para renta cada mes"
Output: {{
    "concepto": "Renta",
    "monto": 500.0,
    "categoria": "General",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
}}

Ejemplo válido para varios gastos fijos:
Input: "Registrar pago de agua $200 mensual y Netflix $139 mensual"
Output: [
  {{
    "concepto": "Agua",
    "monto": 200.0,
    "categoria": "Servicios",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
  }},
  {{
    "concepto": "Netflix",
    "monto": 139.0,
    "categoria": "Entretenimiento",
    "periodicidad": "mensual",
    "fecha_inicio": "{datetime.now().strftime('%Y-%m-%d')}"
  }}
]

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_gastos_fijos_node: {response}")
        raw_parsed_data = parse_json_from_text(response)
        if not raw_parsed_data:
            return {
                **state,
                "parsed_data": None,
                "final_response": "❌ No pude entender la información de los gastos fijos. Intenta con formato: 'Agrega un gasto fijo de $500 para renta cada mes' o lista de ellos."
            }
        if not isinstance(raw_parsed_data, list):
            raw_parsed_data = [raw_parsed_data]
        valid_gastos = []
        errors = []
        for item in raw_parsed_data:
            try:
                gasto = GastoFijo(**item)
                valid_gastos.append(gasto.dict())
            except ValidationError as e:
                errors.append(f"Error en un gasto fijo: {e.errors()}")
            except Exception as e:
                errors.append(f"Error inesperado al validar un gasto fijo: {e}")
        if not valid_gastos:
            return {
                **state,
                "parsed_data": None,
                "final_response": f"❌ No se pudo validar ningún gasto fijo. Errores: {'; '.join(errors) if errors else 'Desconocido'}"
            }
        return {
            **state,
            "parsed_data": valid_gastos
        }
    except Exception as e:
        print(f"❌ Error en parse_gastos_fijos_node: {e}")
        return {
            **state,
            "parsed_data": None,
            "final_response": "❌ Error interno al procesar el gasto fijo. Por favor, intenta de nuevo."
        }

def save_gastos_fijos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que guarda uno o varios gastos fijos parseados en la base de datos.
    Ahora verifica que el usuario exista en la tabla usuarios antes de registrar el gasto fijo.
    """
    parsed_gastos = state.get("parsed_data")
    if not parsed_gastos or not isinstance(parsed_gastos, list):
        return {
            **state,
            "final_response": "❌ No hay datos válidos (lista de gastos fijos) para guardar."
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
        for data in parsed_gastos:
            categoria_nombre = data.get("categoria", "General").capitalize()
            # Buscar o crear la categoría
            cursor.execute("SELECT id FROM categorias WHERE nombre = ?", (categoria_nombre,))
            row = cursor.fetchone()
            if row:
                categoria_id = row[0]
            else:
                cursor.execute("INSERT INTO categorias (nombre, tipo) VALUES (?, 'gasto')", (categoria_nombre,))
                categoria_id = cursor.lastrowid
                conn.commit()
            fecha_inicio = data.get("fecha_inicio") or datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                INSERT INTO gastos_fijos (user_id, categoria_id, concepto, monto, fecha_inicio, periodicidad)
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
        final_response_text = f"✅ Se registraron {saved_count} gastos fijos:\n" + "\n".join(response_messages)
        return {
            **state,
            "final_response": final_response_text
        }
    except Exception as e:
        print(f"❌ Error al guardar en DB en save_gastos_fijos_node: {e}")
        return {
            **state,
            "final_response": "❌ Error al guardar los gastos fijos en la base de datos. Por favor, intenta de nuevo."
        }

def listar_gastos_fijos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que lista todos los gastos fijos del usuario, mostrando ID, concepto, monto, categoría, periodicidad y fecha de inicio.
    """
    user_id = state.get("user_id", "1234")
    try:
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT gf.id, gf.concepto, gf.monto, c.nombre as categoria, gf.periodicidad, gf.fecha_inicio
            FROM gastos_fijos gf
            LEFT JOIN categorias c ON gf.categoria_id = c.id
            WHERE gf.user_id = ?
            ORDER BY gf.fecha_inicio DESC, gf.id DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No hay gastos fijos registrados."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "📋 Gastos fijos registrados:\n" + "\n".join(lines)
        return {**state, "final_response": response}
    except Exception as e:
        print(f"❌ Error al listar gastos fijos: {e}")
        return {**state, "final_response": "❌ Error al listar los gastos fijos. Por favor, intenta de nuevo."}

def parse_editar_gasto_fijo_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para editar un gasto fijo.
    Extrae el ID y los campos a modificar. Si la información es ambigua, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere editar un gasto fijo. Extrae el ID del gasto fijo y los campos a modificar (concepto, monto, categoría, periodicidad, fecha_inicio).
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID y los nuevos valores, responde SOLO con un objeto JSON con los campos a modificar.

Ejemplo:
Input: "Cambia el monto del gasto fijo 5 a 800"
Output: {{"id": 5, "monto": 800}}
Input: "Edita el gasto fijo de Netflix a 150"
Output: {{"busqueda": "Netflix"}}
Input: "Cambia la periodicidad del gasto fijo 3 a quincenal"
Output: {{"id": 3, "periodicidad": "quincenal"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_editar_gasto_fijo_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_editar_gasto_fijo_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué gasto fijo editar."}

def editar_gasto_fijo_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que edita un gasto fijo por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para editar el gasto fijo."}
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT gf.id, gf.concepto, gf.monto, c.nombre as categoria, gf.periodicidad, gf.fecha_inicio
            FROM gastos_fijos gf
            LEFT JOIN categorias c ON gf.categoria_id = c.id
            WHERE gf.user_id = ? AND (gf.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY gf.fecha_inicio DESC, gf.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron gastos fijos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "Se encontraron varios gastos fijos. Por favor, indica el ID a editar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para editar
        set_user_state(user_id, {"pending_action": "editar_gasto_fijo"})
        return {**state, "final_response": response}
    # Si tiene ID y campos a modificar
    id_gasto = data.get("id")
    if not id_gasto:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del gasto fijo a editar."}
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
            cursor.execute("INSERT INTO categorias (nombre, tipo) VALUES (?, 'gasto')", (categoria_nombre,))
            categoria_id = cursor.lastrowid
            conn.commit()
        campos.append("categoria_id = ?")
        valores.append(categoria_id)
    if not campos:
        conn.close()
        return {**state, "final_response": "❌ No se especificó ningún campo a modificar."}
    valores.append(id_gasto)
    cursor.execute(f"UPDATE gastos_fijos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", (*valores, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"✅ Gasto fijo {id_gasto} actualizado correctamente."}

def parse_eliminar_gasto_fijo_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para eliminar un gasto fijo.
    Extrae el ID o una búsqueda. Si es ambiguo, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere eliminar un gasto fijo. Extrae el ID del gasto fijo o una búsqueda por concepto/categoría.
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID, responde SOLO con un objeto JSON con "id": número.

Ejemplo:
Input: "Elimina el gasto fijo 7"
Output: {{"id": 7}}
Input: "Elimina el gasto fijo de agua"
Output: {{"busqueda": "agua"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_eliminar_gasto_fijo_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_eliminar_gasto_fijo_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué gasto fijo eliminar."}

def eliminar_gasto_fijo_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que elimina un gasto fijo por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para eliminar el gasto fijo."}
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT gf.id, gf.concepto, gf.monto, c.nombre as categoria, gf.periodicidad, gf.fecha_inicio
            FROM gastos_fijos gf
            LEFT JOIN categorias c ON gf.categoria_id = c.id
            WHERE gf.user_id = ? AND (gf.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY gf.fecha_inicio DESC, gf.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron gastos fijos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | ${row[2]:.2f} | {row[3] or 'General'} | {row[4]} | desde {row[5]}" for row in rows]
        response = "Se encontraron varios gastos fijos. Por favor, indica el ID a eliminar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para eliminar
        set_user_state(user_id, {"pending_action": "eliminar_gasto_fijo"})
        return {**state, "final_response": response}
    # Si tiene ID
    id_gasto = data.get("id")
    if not id_gasto:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del gasto fijo a eliminar."}
    cursor.execute("DELETE FROM gastos_fijos WHERE id = ? AND user_id = ?", (id_gasto, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"🗑️ Gasto fijo {id_gasto} eliminado correctamente."} 