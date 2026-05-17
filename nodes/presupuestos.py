from typing import Dict, Any
from datetime import datetime
from db import get_conn, upsert_usuario, get_or_create_categoria
from utils.json_parser import parse_json_from_text


def crear_presupuesto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""Extrae la información del presupuesto del siguiente texto.
Responde SOLO con un objeto JSON:
{{
    "categoria": "string",
    "monto_limite": float,
    "periodo": "mensual" | "quincenal" | "semanal"
}}

Ejemplo:
Input: "Quiero un presupuesto de $3000 mensuales para despensa"
Output: {{"categoria": "Despensa", "monto_limite": 3000.0, "periodo": "mensual"}}

Input: "{user_input}"
Output:"""
    response = llm.invoke(prompt)
    data = parse_json_from_text(response)
    if not data or "monto_limite" not in data:
        return {**state, "final_response": "❌ No pude entender el presupuesto. Ejemplo: 'Presupuesto de $3000 mensuales para despensa'"}

    user_id = state.get("user_id", "1234")
    username = state.get("username", "Desconocido")
    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        categoria_id = get_or_create_categoria(conn, data.get("categoria", "General"), "gasto")
        conn.execute(
            '''INSERT INTO presupuestos (user_id, categoria_id, monto_limite, periodo)
               VALUES (?, ?, ?, ?)''',
            (user_id, categoria_id, data["monto_limite"], data.get("periodo", "mensual"))
        )
    return {**state, "final_response": f"✅ Presupuesto de ${data['monto_limite']:.2f} {data.get('periodo','mensual')} creado para {data.get('categoria','General')}."}


def ver_presupuesto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    user_id = state.get("user_id", "1234")
    hoy = datetime.now()
    mes_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
    mes_fin = hoy.strftime('%Y-%m-%d')

    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT p.id, c.nombre, p.monto_limite, p.periodo,
                      COALESCE((
                          SELECT SUM(m.monto) FROM movimientos m
                          LEFT JOIN categorias mc ON m.categoria_id = mc.id
                          WHERE m.user_id = p.user_id
                            AND mc.nombre = c.nombre
                            AND m.fecha BETWEEN ? AND ?
                      ), 0) as gastado
               FROM presupuestos p
               LEFT JOIN categorias c ON p.categoria_id = c.id
               WHERE p.user_id = ?''',
            (mes_inicio, mes_fin, user_id)
        ).fetchall()

    if not rows:
        return {**state, "final_response": "ℹ️ No tienes presupuestos configurados."}

    lines = []
    for r in rows:
        pct = (r["gastado"] / r["monto_limite"] * 100) if r["monto_limite"] else 0
        barra = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        lines.append(
            f"ID:{r['id']} {r['nombre']} [{r['periodo']}]\n"
            f"  {barra} {pct:.0f}%  ${r['gastado']:.2f} / ${r['monto_limite']:.2f}"
        )
    return {**state, "final_response": "📊 Presupuestos:\n\n" + "\n\n".join(lines)}


def editar_presupuesto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere editar un presupuesto.
Responde SOLO con un objeto JSON con "id" y los campos a cambiar (monto_limite, periodo, categoria):
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or "id" not in data:
        return {**state, "final_response": "❌ Indica el ID del presupuesto a editar. Usa 'ver presupuestos' para ver los IDs."}

    user_id = state.get("user_id", "1234")
    campos, valores = [], []
    with get_conn() as conn:
        if "monto_limite" in data:
            campos.append("monto_limite = ?"); valores.append(data["monto_limite"])
        if "periodo" in data:
            campos.append("periodo = ?"); valores.append(data["periodo"])
        if "categoria" in data:
            cat_id = get_or_create_categoria(conn, data["categoria"], "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos:
            return {**state, "final_response": "❌ No se especificó ningún campo a modificar."}
        valores.extend([data["id"], user_id])
        conn.execute(f"UPDATE presupuestos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
    return {**state, "final_response": f"✅ Presupuesto {data['id']} actualizado."}


def eliminar_presupuesto_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario quiere eliminar un presupuesto. Extrae el ID.
Responde SOLO con: {{"id": número}}
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or "id" not in data:
        return {**state, "final_response": "❌ Indica el ID del presupuesto a eliminar."}

    user_id = state.get("user_id", "1234")
    with get_conn() as conn:
        conn.execute("DELETE FROM presupuestos WHERE id = ? AND user_id = ?", (data["id"], user_id))
    return {**state, "final_response": f"🗑️ Presupuesto {data['id']} eliminado."}
