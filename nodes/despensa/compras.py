from typing import Dict, Any
from datetime import datetime, timedelta
from db import get_conn, upsert_usuario
from utils.json_parser import parse_json_from_text


# ── Patrón interno ─────────────────────────────────────────────────────────────

def recalcular_patron(conn, producto_id: int):
    """Recalcula frecuencia promedio y próxima compra estimada para un producto."""
    rows = conn.execute(
        "SELECT fecha FROM compras_despensa WHERE producto_id = ? ORDER BY fecha ASC",
        (producto_id,)
    ).fetchall()

    num = len(rows)
    if num == 0:
        conn.execute("DELETE FROM patrones_despensa WHERE producto_id = ?", (producto_id,))
        return

    ultima = rows[-1]["fecha"]

    if num >= 2:
        fechas = [datetime.strptime(r["fecha"], "%Y-%m-%d") for r in rows]
        intervalos = [(fechas[i+1] - fechas[i]).days for i in range(len(fechas)-1)]
        frec = sum(intervalos) / len(intervalos)
        proxima = (datetime.strptime(ultima, "%Y-%m-%d") + timedelta(days=frec)).strftime("%Y-%m-%d")
    else:
        frec = None
        proxima = None

    conn.execute(
        '''INSERT INTO patrones_despensa (producto_id, frec_prom_dias, ultima_compra, proxima_estimada, num_registros, updated_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(producto_id) DO UPDATE SET
               frec_prom_dias = excluded.frec_prom_dias,
               ultima_compra = excluded.ultima_compra,
               proxima_estimada = excluded.proxima_estimada,
               num_registros = excluded.num_registros,
               updated_at = CURRENT_TIMESTAMP''',
        (producto_id, frec, ultima, proxima, num)
    )


# ── Nodos CRUD ────────────────────────────────────────────────────────────────

def registrar_compra_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    hoy = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""El usuario registra una compra de despensa. Extrae los datos.
Responde SOLO con un objeto JSON o lista de objetos JSON:
{{
    "producto": "string",
    "precio": float o null,
    "cantidad": float (default 1),
    "tienda": "string o null",
    "fecha": "YYYY-MM-DD (default hoy: {hoy})"
}}

Ejemplo:
Input: "Compré Persil en Costco a $370"
Output: {{"producto": "Persil", "precio": 370.0, "cantidad": 1, "tienda": "Costco", "fecha": "{hoy}"}}

Input: "{user_input}"
Output:"""

    data = parse_json_from_text(llm.invoke(prompt))
    if not data:
        return {**state, "final_response": "❌ No entendí la compra. Ejemplo: 'Compré Persil $370 en Costco'"}

    if not isinstance(data, list):
        data = [data]

    user_id = state.get("user_id", "1234")
    username = state.get("username", "Desconocido")
    fuente = "voz" if state.get("es_voz") else "manual"
    registradas, no_encontradas = [], []

    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        for item in data:
            nombre = item.get("producto", "")
            # Buscar por el nombre completo primero; si no, por la primera palabra significativa
            row = conn.execute(
                "SELECT id, nombre FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1 LIMIT 1",
                (user_id, f"%{nombre}%")
            ).fetchone()
            if not row:
                palabras = [p for p in nombre.split() if len(p) > 2]
                for palabra in palabras:
                    row = conn.execute(
                        "SELECT id, nombre FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1 LIMIT 1",
                        (user_id, f"%{palabra}%")
                    ).fetchone()
                    if row:
                        break

            if not row:
                no_encontradas.append(nombre)
                continue

            producto_id = row["id"]
            conn.execute(
                '''INSERT INTO compras_despensa (producto_id, user_id, fecha, precio, cantidad, tienda, fuente)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (producto_id, user_id,
                 item.get("fecha", hoy),
                 item.get("precio"),
                 item.get("cantidad", 1),
                 item.get("tienda"),
                 fuente)
            )
            recalcular_patron(conn, producto_id)
            registradas.append(row["nombre"])

    lines = []
    if registradas:
        lines.append("✅ Compras registradas:\n" + "\n".join(f"• {n}" for n in registradas))
    if no_encontradas:
        lines.append("⚠️ Productos no encontrados en tu despensa (agrégalos primero):\n" + "\n".join(f"• {n}" for n in no_encontradas))

    return {**state, "final_response": "\n\n".join(lines) or "❌ No se registró ninguna compra."}


def listar_compras_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    hoy = datetime.now()
    prompt = f"""El usuario quiere ver su historial de compras de despensa.
Extrae filtros SOLO si el usuario menciona un producto específico o un periodo concreto.
Palabras genéricas como "despensa", "compras", "historial", "todo" NO son filtros de producto.
Responde SOLO con JSON: {{"producto": null, "desde": null, "hasta": null}}
Hoy es {hoy.strftime('%Y-%m-%d')}.
Input: "{user_input}"
Output:"""
    filtro = parse_json_from_text(llm.invoke(prompt)) or {}

    user_id = state.get("user_id", "1234")
    query = '''
        SELECT cd.id, p.nombre, cd.fecha, cd.precio, cd.cantidad, cd.tienda, cd.fuente
        FROM compras_despensa cd
        JOIN productos p ON cd.producto_id = p.id
        WHERE cd.user_id = ?
    '''
    params = [user_id]
    if filtro.get("producto"):
        query += " AND p.nombre LIKE ?"; params.append(f"%{filtro['producto']}%")
    if filtro.get("desde"):
        query += " AND cd.fecha >= ?"; params.append(filtro["desde"])
    if filtro.get("hasta"):
        query += " AND cd.fecha <= ?"; params.append(filtro["hasta"])
    query += " ORDER BY cd.fecha DESC LIMIT 30"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return {**state, "final_response": "ℹ️ No hay compras registradas con ese filtro."}

    lines = []
    for r in rows:
        precio = f"${r['precio']:.2f}" if r['precio'] else "—"
        tienda = r['tienda'] or "—"
        lines.append(f"ID:{r['id']} {r['fecha']} | {r['nombre']} | {precio} x{r['cantidad']} | {tienda}")

    return {**state, "final_response": f"📋 Historial de compras ({len(rows)}):\n" + "\n".join(lines)}


def editar_compra_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere corregir una compra de despensa. Extrae el ID y los campos a cambiar.
Campos posibles: precio, cantidad, tienda, fecha.
Responde SOLO con JSON incluyendo "id".
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or "id" not in data:
        return {**state, "final_response": "❌ Indica el ID de la compra a corregir. Usa 'historial compras' para verlos."}

    # Normalizar variantes de estructura del LLM
    if "campos_a_cambiar" in data and isinstance(data["campos_a_cambiar"], dict):
        data.update(data.pop("campos_a_cambiar"))
    if "campo_a_cambiar" in data and "nuevo_valor" in data:
        data[data.pop("campo_a_cambiar")] = data.pop("nuevo_valor")

    # Convertir id a int si viene como string
    try:
        data["id"] = int(data["id"])
    except (ValueError, TypeError):
        pass

    user_id = state.get("user_id", "1234")
    campos, valores = [], []
    for campo in ("precio", "cantidad", "tienda", "fecha"):
        if campo in data:
            campos.append(f"{campo} = ?"); valores.append(data[campo])

    if not campos:
        return {**state, "final_response": "❌ No se especificó ningún campo a modificar."}

    valores.extend([data["id"], user_id])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT producto_id FROM compras_despensa WHERE id = ? AND user_id = ?",
            (data["id"], user_id)
        ).fetchone()
        if not row:
            return {**state, "final_response": "❌ No se encontró esa compra."}
        conn.execute(f"UPDATE compras_despensa SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
        recalcular_patron(conn, row["producto_id"])

    return {**state, "final_response": f"✅ Compra {data['id']} actualizada."}


def eliminar_compra_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere eliminar un registro de compra. Extrae el ID.
Responde SOLO con JSON: {{"id": número}}
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or "id" not in data:
        return {**state, "final_response": "❌ Indica el ID de la compra a eliminar."}

    user_id = state.get("user_id", "1234")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT producto_id FROM compras_despensa WHERE id = ? AND user_id = ?",
            (data["id"], user_id)
        ).fetchone()
        if not row:
            return {**state, "final_response": "❌ No se encontró esa compra."}
        conn.execute("DELETE FROM compras_despensa WHERE id = ? AND user_id = ?", (data["id"], user_id))
        recalcular_patron(conn, row["producto_id"])

    return {**state, "final_response": f"🗑️ Compra {data['id']} eliminada y patrón actualizado."}
