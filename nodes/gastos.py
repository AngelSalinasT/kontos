# nodes/gastos.py
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime
from nodes.memory import set_user_state
from utils.json_parser import parse_json_from_text

# Modelos Pydantic para la salida estructurada
class Movimiento(BaseModel):
    fecha: str = Field(..., example="05 Julio")
    concepto: str = Field(..., example="Soriana")
    monto: float = Field(gt=0, example=385.30)
    categoria: str = Field("General", example="Comida")  # Campo para categoría

    except Exception as e:
        print(f"❌ General Error parsing JSON in gastos.py: {e} in text: {text[:200]}...")
        return None

def parse_movement_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que parsea la información de uno o varios gastos específicos usando LLM.
    Ahora también extrae o infiere la categoría si está presente o es deducible.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
Extrae la información de los gastos del siguiente texto. Si hay múltiples gastos, devuélvelos como una lista de objetos JSON.

REGLAS:
1. La fecha debe ser en formato "DD Mes" (ej. "05 Julio"). Si no se especifica, usa la fecha actual (ej. "{datetime.now().strftime('%d %B')}").
2. El concepto debe ser una descripción concisa del gasto.
3. El monto debe ser un número flotante positivo.
4. Si el usuario menciona una categoría (ej. comida, transporte, ocio, etc.), inclúyela en el campo "categoria". 
5. Si NO se menciona una categoría, INFIERELA según el concepto del gasto. Ejemplos:
   - Uber Eats, Rappi, Struber eats, Nutrisa, McDonalds, Starbucks → "Comida"
   - Amazon, Mercado Libre, Shein, Liverpool, Zara → "Compras en línea"
   - Gasolina, Uber, Taxi, Metro, Camión → "Transporte"
   - Cine, Netflix, Spotify, Disney+, Cinepolis → "Entretenimiento"
   - Telcel, AT&T, Internet, Teléfono, Luz, Agua, Gas → "Servicios"
   - Farmacia, Doctor, Hospital, Laboratorio → "Salud"
   - UVM, Universidad, Inscripción, Colegiatura → "Educación"
   - Si no puedes inferir la categoría, usa "General".

Responde SOLO con un objeto JSON o una lista de objetos JSON que sigan este esquema Pydantic para cada movimiento:
{{
    "fecha": "string", // Formato "DD Mes"
    "concepto": "string",
    "monto": float, // Mayor que 0
    "categoria": "string" // Ejemplo: "Comida", "Transporte", "General"
}}

Ejemplo válido para un solo movimiento:
Input: "15 Julio Uber Eats $350.50"
Output: {{
    "fecha": "15 Julio",
    "concepto": "Uber Eats",
    "monto": 350.50,
    "categoria": "Comida"
}}

Ejemplo válido para múltiples movimientos:
Input: "05 Julio Amazon $385.30. 04 Julio Gas $710.44. 03 Julio Cine $120"
Output: [
  {{
    "fecha": "05 Julio",
    "concepto": "Amazon",
    "monto": 385.30,
    "categoria": "Compras en línea"
  }},
  {{
    "fecha": "04 Julio",
    "concepto": "Gas",
    "monto": 710.44,
    "categoria": "Servicios"
  }},
  {{
    "fecha": "03 Julio",
    "concepto": "Cine",
    "monto": 120.0,
    "categoria": "Entretenimiento"
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
    Ahora verifica que el usuario exista en la tabla usuarios antes de registrar el gasto.
    Además, autocompleta fechas faltantes para evitar errores de formato.
    """
    parsed_movements = state.get("parsed_data") 
    if not parsed_movements or not isinstance(parsed_movements, list):
        return {
            **state,
            "final_response": "❌ No hay datos válidos (lista de movimientos) para guardar."
        }
    try:
        from tools import insertar_movimiento_tool
        import sqlite3
        saved_count = 0
        response_messages = []
        current_user_id = state.get("user_id", "1234")
        current_username = state.get("username", "Desconocido")
        # Verificar o crear usuario
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM usuarios WHERE user_id = ?", (current_user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios (user_id, username) VALUES (?, ?)", (current_user_id, current_username))
            conn.commit()
        from datetime import datetime
        now = datetime.now()
        for data in parsed_movements:
            fecha_str = data.get("fecha", "").strip()
            # --- Autocompletar fecha ---
            fecha_con_ano = None
            try:
                # Caso 1: "DD Mes" (ej. "03 Julio")
                try:
                    fecha_obj = datetime.strptime(fecha_str, '%d %B')
                    fecha_con_ano = fecha_obj.replace(year=now.year).strftime('%d %B %Y')
                except ValueError:
                    # Caso 2: Solo "Mes" (ej. "Julio")
                    try:
                        fecha_obj = datetime.strptime(fecha_str, '%B')
                        fecha_obj = fecha_obj.replace(day=now.day, year=now.year)
                        fecha_con_ano = fecha_obj.strftime('%d %B %Y')
                    except ValueError:
                        # Caso 3: Solo "DD" (ej. "03")
                        try:
                            fecha_obj = datetime.strptime(fecha_str, '%d')
                            fecha_obj = fecha_obj.replace(month=now.month, year=now.year)
                            fecha_con_ano = fecha_obj.strftime('%d %B %Y')
                        except ValueError:
                            # Caso 4: Si no hay fecha o formato desconocido, usa fecha actual
                            fecha_con_ano = now.strftime('%d %B %Y')
            except Exception:
                fecha_con_ano = now.strftime('%d %B %Y')
            # --- Fin autocompletar fecha ---
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
            insertar_movimiento_tool(
                user_id=current_user_id,
                username=current_username,
                fecha=fecha_con_ano,
                concepto=data["concepto"],
                monto=data["monto"],
                categoria_id=categoria_id,
                origen="Telegram"
            )
            saved_count += 1
            response_messages.append(f"✅ {data['concepto']} ${data['monto']:.2f} [{categoria_nombre}]")
        conn.close()
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

def parse_listar_gastos_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para determinar el mes a listar.
    Si no se especifica, usa el mes actual.
    """
    user_input = state["messages"][-1].content
    today = datetime.today()
    prompt = f"""
El usuario pregunta: "{user_input}"

Determina el mes y año para listar los gastos. Si no se especifica, usa el mes actual.
Responde SOLO con un objeto JSON:
{{
    "mes": "MM", // mes en dos dígitos
    "anio": "YYYY" // año en cuatro dígitos
}}

Ejemplo:
Input: "listar gastos de julio"
Output: {{ "mes": "07", "anio": "{today.year}" }}
Input: "gastos de marzo 2023"
Output: {{ "mes": "03", "anio": "2023" }}
Input: "listar gastos"
Output: {{ "mes": "{today.strftime('%m')}", "anio": "{today.year}" }}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_listar_gastos_node: {response}")
        data = parse_json_from_text(response)
        if not data or "mes" not in data or "anio" not in data:
            data = {"mes": today.strftime('%m'), "anio": str(today.year)}
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_listar_gastos_node: {e}")
        return {**state, "parsed_data": {"mes": today.strftime('%m'), "anio": str(today.year)}, "final_response": "❌ No pude entender el mes. Mostrando gastos del mes actual."}

def listar_gastos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que lista los gastos del usuario para el mes y año especificados.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    mes = data.get("mes")
    anio = data.get("anio")
    try:
        import sqlite3
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        fecha_inicio = f"{anio}-{mes}-01"
        if mes == '12':
            fecha_fin = f"{int(anio)+1}-01-01"
        else:
            fecha_fin = f"{anio}-{str(int(mes)+1).zfill(2)}-01"
        cursor.execute('''
            SELECT m.id, m.fecha, m.concepto, m.monto, c.nombre as categoria
            FROM movimientos m
            LEFT JOIN categorias c ON m.categoria_id = c.id
            WHERE m.user_id = ? AND m.fecha >= ? AND m.fecha < ?
            ORDER BY m.fecha DESC, m.id DESC
        ''', (user_id, fecha_inicio, fecha_fin))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": f"ℹ️ No hay gastos registrados para {mes}/{anio}."}
        lines = [f"ID: {row[0]} | {row[1]} | {row[2]} | ${row[3]:.2f} | {row[4] or 'General'}" for row in rows]
        response = f"📋 Gastos de {mes}/{anio}:\n" + "\n".join(lines)
        return {**state, "final_response": response}
    except Exception as e:
        print(f"❌ Error al listar gastos: {e}")
        return {**state, "final_response": "❌ Error al listar los gastos. Por favor, intenta de nuevo."}

def parse_editar_gasto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para editar un gasto.
    Extrae el ID y los campos a modificar. Si la información es ambigua, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere editar un gasto. Extrae el ID del gasto y los campos a modificar (fecha, concepto, monto, categoría).
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID y los nuevos valores, responde SOLO con un objeto JSON con los campos a modificar.

Ejemplo:
Input: "Cambia el monto del gasto 12 a 300"
Output: {{"id": 12, "monto": 300}}
Input: "Edita el gasto de Netflix a 150"
Output: {{"busqueda": "Netflix"}}
Input: "Cambia la categoría del gasto 8 a Entretenimiento"
Output: {{"id": 8, "categoria": "Entretenimiento"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_editar_gasto_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_editar_gasto_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué gasto editar."}

def editar_gasto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que edita un gasto por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para editar el gasto."}
    import sqlite3
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT m.id, m.fecha, m.concepto, m.monto, c.nombre as categoria
            FROM movimientos m
            LEFT JOIN categorias c ON m.categoria_id = c.id
            WHERE m.user_id = ? AND (m.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY m.fecha DESC, m.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron gastos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | {row[2]} | ${row[3]:.2f} | {row[4] or 'General'}" for row in rows]
        response = "Se encontraron varios gastos. Por favor, indica el ID a editar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para editar
        set_user_state(user_id, {"pending_action": "editar_gasto"})
        return {**state, "final_response": response}
    # Si tiene ID y campos a modificar
    id_gasto = data.get("id")
    if not id_gasto:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del gasto a editar."}
    campos = []
    valores = []
    if "fecha" in data:
        campos.append("fecha = ?")
        valores.append(data["fecha"])
    if "concepto" in data:
        campos.append("concepto = ?")
        valores.append(data["concepto"])
    if "monto" in data:
        campos.append("monto = ?")
        valores.append(data["monto"])
    if "categoria" in data:
        # Buscar o crear la categoría
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
    cursor.execute(f"UPDATE movimientos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", (*valores, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"✅ Gasto {id_gasto} actualizado correctamente."}

def parse_eliminar_gasto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Nodo que interpreta el mensaje del usuario para eliminar un gasto.
    Extrae el ID o una búsqueda. Si es ambiguo, el LLM debe sugerir opciones.
    """
    user_input = state["messages"][-1].content
    prompt = f"""
El usuario quiere eliminar un gasto. Extrae el ID del gasto o una búsqueda por concepto/categoría.
Si el usuario no especifica el ID pero da una descripción, responde SOLO con un objeto JSON con "busqueda": "texto de búsqueda".
Si el usuario da el ID, responde SOLO con un objeto JSON con "id": número.

Ejemplo:
Input: "Elimina el gasto 15"
Output: {{"id": 15}}
Input: "Elimina el gasto de agua"
Output: {{"busqueda": "agua"}}

Input: "{user_input}"
Output:"""
    try:
        response = llm.invoke(prompt)
        print(f"🔎 Raw LLM response for parse_eliminar_gasto_node: {response}")
        data = parse_json_from_text(response)
        return {**state, "parsed_data": data}
    except Exception as e:
        print(f"❌ Error en parse_eliminar_gasto_node: {e}")
        return {**state, "parsed_data": None, "final_response": "❌ No pude entender qué gasto eliminar."}

def eliminar_gasto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que elimina un gasto por ID o ayuda a buscarlo si la información es ambigua.
    """
    data = state.get("parsed_data")
    user_id = state.get("user_id", "1234")
    if not data:
        return {**state, "final_response": "❌ No se proporcionó información suficiente para eliminar el gasto."}
    import sqlite3
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    # Si es búsqueda ambigua
    if "busqueda" in data:
        texto = f"%{data['busqueda']}%"
        cursor.execute('''
            SELECT m.id, m.fecha, m.concepto, m.monto, c.nombre as categoria
            FROM movimientos m
            LEFT JOIN categorias c ON m.categoria_id = c.id
            WHERE m.user_id = ? AND (m.concepto LIKE ? OR c.nombre LIKE ?)
            ORDER BY m.fecha DESC, m.id DESC
        ''', (user_id, texto, texto))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontraron gastos que coincidan con la búsqueda."}
        lines = [f"ID: {row[0]} | {row[1]} | {row[2]} | ${row[3]:.2f} | {row[4] or 'General'}" for row in rows]
        response = "Se encontraron varios gastos. Por favor, indica el ID a eliminar:\n" + "\n".join(lines)
        # Guardar en memoria que se espera un ID para eliminar
        set_user_state(user_id, {"pending_action": "eliminar_gasto"})
        return {**state, "final_response": response}
    # Si tiene ID
    id_gasto = data.get("id")
    if not id_gasto:
        conn.close()
        return {**state, "final_response": "❌ Debes indicar el ID del gasto a eliminar."}
    cursor.execute("DELETE FROM movimientos WHERE id = ? AND user_id = ?", (id_gasto, user_id))
    conn.commit()
    conn.close()
    return {**state, "final_response": f"🗑️ Gasto {id_gasto} eliminado correctamente."}
