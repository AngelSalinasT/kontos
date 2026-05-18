from typing import Dict, Any
from db import get_conn, upsert_usuario, get_or_create_categoria
from utils.json_parser import parse_json_from_text


def crear_producto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""Extrae la información del producto de despensa del texto.
Responde SOLO con un objeto JSON o lista de objetos JSON:
{{
    "nombre": "string",
    "marca": "string o null",
    "categoria": "string",
    "unidad": "pz | L | kg | paquete | caja",
    "precio_ref": float o null,
    "tienda_pref": "string o null"
}}

Ejemplo:
Input: "Agrega Persil líquido 10L de Costco a $370"
Output: {{"nombre": "Persil Líquido", "marca": "Persil", "categoria": "Despensa", "unidad": "L", "precio_ref": 370.0, "tienda_pref": "Costco"}}

Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data:
        return {**state, "final_response": "❌ No pude entender el producto. Ejemplo: 'Agrega Persil 10L de Costco a $370'"}

    if not isinstance(data, list):
        data = [data]

    user_id = state.get("user_id", "1234")
    username = state.get("username", "Desconocido")
    creados = []
    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        for item in data:
            if not item.get("nombre"):
                continue
            cat_id = get_or_create_categoria(conn, item.get("categoria", "Despensa"), "gasto")
            conn.execute(
                '''INSERT INTO productos (user_id, categoria_id, nombre, marca, unidad, precio_ref, tienda_pref)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (user_id, cat_id, item["nombre"], item.get("marca"),
                 item.get("unidad"), item.get("precio_ref"), item.get("tienda_pref"))
            )
            creados.append(item["nombre"])

    if not creados:
        return {**state, "final_response": "❌ No se pudo registrar ningún producto."}
    return {**state, "final_response": f"✅ Productos agregados a tu despensa:\n" + "\n".join(f"• {n}" for n in creados)}


def listar_productos_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    user_id = state.get("user_id", "1234")

    # Detectar filtro explícito (solo si el usuario menciona categoría o tienda específica)
    prompt = f"""El usuario quiere ver productos de su despensa.
¿Menciona EXPLÍCITAMENTE una categoría (ej: "solo higiene", "categoría limpieza") o tienda específica?
"ver despensa", "mis productos", "qué tengo" NO son filtros — devuelve nulls.
Responde SOLO con JSON: {{"categoria": null, "tienda": null, "solo_activos": true}}
Input: "{user_input}"
Output:"""
    filtro = parse_json_from_text(llm.invoke(prompt)) or {}

    query = '''
        SELECT p.id, p.nombre, p.marca, c.nombre as categoria,
               p.unidad, p.precio_ref, p.tienda_pref, p.activo
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.user_id = ?
    '''
    params = [user_id]
    if filtro.get("solo_activos", True):
        query += " AND p.activo = 1"
    if filtro.get("categoria"):
        query += " AND c.nombre LIKE ?"
        params.append(f"%{filtro['categoria']}%")
    if filtro.get("tienda"):
        query += " AND p.tienda_pref LIKE ?"
        params.append(f"%{filtro['tienda']}%")
    query += " ORDER BY c.nombre, p.nombre"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return {**state, "final_response": "ℹ️ No tienes productos en tu despensa. Agrega uno con 'agregar producto'."}

    lines = []
    for r in rows:
        precio = f"${r['precio_ref']:.2f}" if r['precio_ref'] else "—"
        tienda = r['tienda_pref'] or "—"
        lines.append(f"ID:{r['id']} {r['nombre']} ({r['marca'] or '—'}) | {r['unidad'] or '—'} | {precio} | {tienda}")

    return {**state, "final_response": f"🛒 Tu despensa ({len(rows)} productos):\n" + "\n".join(lines)}


def editar_producto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere editar un producto. Extrae el ID y los campos a cambiar.
Si da descripción en vez de ID, usa "busqueda": "texto".
Campos posibles: nombre, marca, unidad, precio_ref, tienda_pref, categoria.
Responde SOLO con JSON.
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data:
        return {**state, "final_response": "❌ No entendí qué producto editar."}

    # El LLM a veces anida los campos en "campos_a_cambiar" — aplanar
    if "campos_a_cambiar" in data and isinstance(data["campos_a_cambiar"], dict):
        data.update(data.pop("campos_a_cambiar"))

    user_id = state.get("user_id", "1234")

    if "busqueda" in data:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, nombre, marca, tienda_pref FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1",
                (user_id, f"%{data['busqueda']}%")
            ).fetchall()
        if not rows:
            return {**state, "final_response": "ℹ️ No se encontró el producto. Usa 'ver despensa' para ver IDs."}
        lines = [f"ID:{r['id']} {r['nombre']} ({r['marca'] or '—'}) {r['tienda_pref'] or ''}" for r in rows]
        return {**state, "final_response": "¿Cuál quieres editar? Dime el ID:\n" + "\n".join(lines)}

    if "id" not in data:
        return {**state, "final_response": "❌ Indica el ID del producto a editar."}

    campos, valores = [], []
    # "precio" es alias de "precio_ref" para facilitar el lenguaje natural
    if "precio" in data and "precio_ref" not in data:
        data["precio_ref"] = data.pop("precio")

    with get_conn() as conn:
        for campo in ("nombre", "marca", "unidad", "precio_ref", "tienda_pref"):
            if campo in data:
                campos.append(f"{campo} = ?"); valores.append(data[campo])
        if "categoria" in data:
            cat_id = get_or_create_categoria(conn, data["categoria"], "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos:
            return {**state, "final_response": "❌ No se especificó ningún campo a modificar."}
        valores.extend([data["id"], user_id])
        conn.execute(f"UPDATE productos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)

    return {**state, "final_response": f"✅ Producto {data['id']} actualizado."}


def desactivar_producto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere quitar un producto de su despensa. Extrae el ID o nombre.
Responde SOLO con JSON: {{"id": número}} o {{"busqueda": "texto"}}
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data:
        return {**state, "final_response": "❌ No entendí qué producto desactivar."}

    user_id = state.get("user_id", "1234")

    if "busqueda" in data:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, nombre FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1",
                (user_id, f"%{data['busqueda']}%")
            ).fetchall()
        if not rows:
            return {**state, "final_response": "ℹ️ Producto no encontrado."}
        if len(rows) == 1:
            pid = rows[0]["id"]
            nombre = rows[0]["nombre"]
        else:
            lines = [f"ID:{r['id']} {r['nombre']}" for r in rows]
            return {**state, "final_response": "¿Cuál quieres desactivar? Dime el ID:\n" + "\n".join(lines)}
    else:
        pid = data.get("id")
        nombre = f"ID {pid}"

    with get_conn() as conn:
        conn.execute("UPDATE productos SET activo = 0 WHERE id = ? AND user_id = ?", (pid, user_id))

    return {**state, "final_response": f"✅ '{nombre}' quitado de tu despensa (puedes reactivarlo si lo necesitas)."}
