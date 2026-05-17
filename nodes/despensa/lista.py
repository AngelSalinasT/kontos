from typing import Dict, Any
from datetime import datetime, timedelta
from db import get_conn
from utils.json_parser import parse_json_from_text

MIN_REGISTROS_PATRON = 3
DIAS_ADELANTO = 7  # mostrar productos que toca comprar en los próximos N días


def generar_lista_despensa_node(state: Dict[str, Any]) -> Dict[str, Any]:
    user_id = state.get("user_id", "1234")
    hoy = datetime.now().strftime("%Y-%m-%d")
    limite = (datetime.now() + timedelta(days=DIAS_ADELANTO)).strftime("%Y-%m-%d")

    with get_conn() as conn:
        # Productos activos con su patrón
        rows = conn.execute(
            '''SELECT p.id, p.nombre, p.marca, p.precio_ref, p.tienda_pref, p.unidad,
                      pd.frec_prom_dias, pd.ultima_compra, pd.proxima_estimada, pd.num_registros
               FROM productos p
               LEFT JOIN patrones_despensa pd ON p.id = pd.producto_id
               WHERE p.user_id = ? AND p.activo = 1
               ORDER BY p.nombre''',
            (user_id,)
        ).fetchall()

    if not rows:
        return {**state, "final_response": "ℹ️ No tienes productos en tu despensa. Agrega uno con 'agregar producto'."}

    # Clasificar: con patrón suficiente vs sin datos
    con_patron = [r for r in rows if (r["num_registros"] or 0) >= MIN_REGISTROS_PATRON]
    sin_datos = [r for r in rows if (r["num_registros"] or 0) < MIN_REGISTROS_PATRON]

    if not con_patron:
        # Cold start — mostrar lista completa y pedir confirmación
        lines = []
        for r in rows:
            precio = f"${r['precio_ref']:.2f}" if r['precio_ref'] else "—"
            tienda = r['tienda_pref'] or "—"
            registros = r['num_registros'] or 0
            lines.append(f"• {r['nombre']} ({r['marca'] or '—'}) | {precio} | {tienda} | {registros} registros")

        return {**state, "final_response": (
            "🛒 Lista completa de tu despensa\n"
            "_(Aún no tengo suficientes datos para predecir — necesito al menos 3 compras por producto)_\n\n"
            + "\n".join(lines)
            + "\n\n📝 Cuando termines de comprar, dime qué compraste para ir aprendiendo tu patrón."
        )}

    # Con patrón — filtrar los que toca comprar pronto
    toca_comprar = [r for r in con_patron if r["proxima_estimada"] and r["proxima_estimada"] <= limite]
    pronto = [r for r in con_patron if r["proxima_estimada"] and limite < r["proxima_estimada"]]

    lines_comprar = []
    for r in toca_comprar:
        precio = f"${r['precio_ref']:.2f}" if r['precio_ref'] else "—"
        tienda = r['tienda_pref'] or "—"
        dias_restantes = (datetime.strptime(r["proxima_estimada"], "%Y-%m-%d") - datetime.now()).days
        urgencia = "⚠️ YA" if dias_restantes <= 0 else f"en {dias_restantes}d"
        lines_comprar.append(f"• {r['nombre']} | {precio} | {tienda} | {urgencia}")

    lines_pronto = []
    for r in pronto:
        dias = (datetime.strptime(r["proxima_estimada"], "%Y-%m-%d") - datetime.now()).days
        lines_pronto.append(f"• {r['nombre']} — en ~{dias} días")

    lines_sin_datos = [f"• {r['nombre']} ({r['num_registros'] or 0} registros)" for r in sin_datos]

    respuesta = f"🛒 Lista de despensa — {hoy}\n"

    if lines_comprar:
        respuesta += f"\n🔴 Comprar ahora ({len(lines_comprar)}):\n" + "\n".join(lines_comprar)
    else:
        respuesta += "\n✅ Todo al día, no hay nada urgente."

    if lines_pronto:
        respuesta += f"\n\n🟡 Próximamente:\n" + "\n".join(lines_pronto)

    if lines_sin_datos:
        respuesta += f"\n\n⚪ Sin patrón aún (necesitan más compras):\n" + "\n".join(lines_sin_datos)

    return {**state, "final_response": respuesta}


def consultar_prediccion_node(state: Dict[str, Any], llm) -> Dict[str, Any]:
    user_input = state["messages"][-1].content
    prompt = f"""El usuario pregunta cuándo debe comprar un producto específico.
Extrae el nombre del producto.
Responde SOLO con JSON: {{"producto": "string"}}
Input: "{user_input}"
Output:"""
    data = parse_json_from_text(llm.invoke(prompt))
    if not data or not data.get("producto"):
        return {**state, "final_response": "❌ No entendí de qué producto quieres la predicción."}

    user_id = state.get("user_id", "1234")
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT p.nombre, p.precio_ref, p.tienda_pref,
                      pd.frec_prom_dias, pd.ultima_compra, pd.proxima_estimada, pd.num_registros
               FROM productos p
               LEFT JOIN patrones_despensa pd ON p.id = pd.producto_id
               WHERE p.user_id = ? AND p.nombre LIKE ? AND p.activo = 1
               LIMIT 1''',
            (user_id, f"%{data['producto']}%")
        ).fetchone()

    if not row:
        return {**state, "final_response": f"❌ No encontré '{data['producto']}' en tu despensa."}

    num = row["num_registros"] or 0
    if num < MIN_REGISTROS_PATRON:
        return {**state, "final_response": (
            f"📊 {row['nombre']}: solo tengo {num} registro(s). "
            f"Necesito al menos {MIN_REGISTROS_PATRON} compras para predecir con confianza."
        )}

    dias = int(row["frec_prom_dias"])
    proxima = row["proxima_estimada"]
    dias_restantes = (datetime.strptime(proxima, "%Y-%m-%d") - datetime.now()).days
    precio = f"${row['precio_ref']:.2f}" if row['precio_ref'] else "precio no registrado"
    tienda = row['tienda_pref'] or "tienda no especificada"

    estado = "⚠️ Ya debería haberlo comprado" if dias_restantes < 0 else f"en {dias_restantes} días ({proxima})"

    return {**state, "final_response": (
        f"📊 Predicción — {row['nombre']}\n"
        f"• Frecuencia promedio: cada {dias} días\n"
        f"• Última compra: {row['ultima_compra']}\n"
        f"• Próxima estimada: {estado}\n"
        f"• Precio referencia: {precio}\n"
        f"• Tienda: {tienda}\n"
        f"• Basado en {num} compras registradas"
    )}
