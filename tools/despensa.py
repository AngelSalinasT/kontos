from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool
from db import get_conn, upsert_usuario, get_or_create_categoria
from context import get_user_id, get_username


def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _recalcular_patron(conn, producto_id: int):
    rows = conn.execute(
        "SELECT fecha FROM compras_despensa WHERE producto_id = ? ORDER BY fecha ASC", (producto_id,)
    ).fetchall()
    num = len(rows)
    if num == 0:
        conn.execute("DELETE FROM patrones_despensa WHERE producto_id = ?", (producto_id,)); return
    ultima = rows[-1]["fecha"]
    if num >= 2:
        fechas = [datetime.strptime(r["fecha"], "%Y-%m-%d") for r in rows]
        intervalos = [(fechas[i + 1] - fechas[i]).days for i in range(len(fechas) - 1)]
        frec = sum(intervalos) / len(intervalos)
        proxima = (datetime.strptime(ultima, "%Y-%m-%d") + timedelta(days=frec)).strftime("%Y-%m-%d")
    else:
        frec = proxima = None
    conn.execute(
        """INSERT INTO patrones_despensa (producto_id, frec_prom_dias, ultima_compra, proxima_estimada, num_registros, updated_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(producto_id) DO UPDATE SET frec_prom_dias=excluded.frec_prom_dias,
           ultima_compra=excluded.ultima_compra, proxima_estimada=excluded.proxima_estimada,
           num_registros=excluded.num_registros, updated_at=CURRENT_TIMESTAMP""",
        (producto_id, frec, ultima, proxima, num),
    )


# ── Productos ─────────────────────────────────────────────────────────────────

@tool
def agregar_producto_despensa(nombre: str, tienda: Optional[str] = None, unidad: Optional[str] = None, marca: Optional[str] = None, categoria: str = "Despensa") -> str:
    """Agrega un nuevo producto al catálogo de despensa. No registra una compra, solo agrega el producto.
    Úsala cuando el usuario quiera agregar un producto que compra regularmente.

    Args:
        nombre: Nombre del producto (ej: 'Leche Deslactosada', 'Papel Higiénico')
        tienda: Donde se compra: 'Costco', 'Supermarket', 'Walmart', etc.
        unidad: 'pz', 'L', 'kg', 'paquete', 'caja'
        marca: Marca del producto (opcional)
        categoria: 'Despensa', 'Limpieza', 'Higiene', etc.
    """
    user_id = get_user_id()
    with get_conn() as conn:
        upsert_usuario(conn, user_id, get_username())
        cat_id = get_or_create_categoria(conn, categoria, "gasto")
        conn.execute(
            "INSERT INTO productos (user_id, categoria_id, nombre, marca, unidad, tienda_pref) VALUES (?,?,?,?,?,?)",
            (user_id, cat_id, nombre, marca, unidad, tienda),
        )
    return f"✅ Producto agregado: {nombre}" + (f" ({tienda})" if tienda else "")


@tool
def listar_productos_despensa(categoria: Optional[str] = None, tienda: Optional[str] = None) -> str:
    """Lista los productos activos de la despensa.
    Úsala cuando el usuario pida ver su despensa, sus productos o qué tiene registrado.

    Args:
        categoria: Filtrar por categoría (ej: 'Limpieza'). Omitir para ver todos.
        tienda: Filtrar por tienda (ej: 'Costco'). Omitir para ver todos.
    """
    user_id = get_user_id()
    query = """SELECT p.id, p.nombre, p.marca, c.nombre as cat, p.unidad, p.tienda_pref
               FROM productos p LEFT JOIN categorias c ON p.categoria_id = c.id
               WHERE p.user_id = ? AND p.activo = 1"""
    params = [user_id]
    if categoria: query += " AND c.nombre LIKE ?"; params.append(f"%{categoria}%")
    if tienda: query += " AND p.tienda_pref LIKE ?"; params.append(f"%{tienda}%")
    query += " ORDER BY c.nombre, p.nombre"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    if not rows:
        return "ℹ️ No tienes productos en tu despensa. Agrega uno diciéndome qué compras regularmente."
    lines = [
        f"ID:{r['id']} {r['nombre']}" + (f" ({r['marca']})" if r['marca'] else "") +
        f" | {r['unidad'] or '—'} | {r['tienda_pref'] or '—'}"
        for r in rows
    ]
    return f"🛒 Tu despensa ({len(rows)} productos):\n" + "\n".join(lines)


@tool
def editar_producto_despensa(id: int, nombre: Optional[str] = None, marca: Optional[str] = None, unidad: Optional[str] = None, tienda: Optional[str] = None, categoria: Optional[str] = None) -> str:
    """Edita un producto de la despensa por su ID. Usa listar_productos_despensa primero si el usuario no sabe el ID.

    Args:
        id: ID del producto
        nombre: Nuevo nombre (opcional)
        marca: Nueva marca (opcional)
        unidad: Nueva unidad (opcional)
        tienda: Nueva tienda preferida (opcional)
        categoria: Nueva categoría (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []
    with get_conn() as conn:
        if nombre: campos.append("nombre = ?"); valores.append(nombre)
        if marca: campos.append("marca = ?"); valores.append(marca)
        if unidad: campos.append("unidad = ?"); valores.append(unidad)
        if tienda: campos.append("tienda_pref = ?"); valores.append(tienda)
        if categoria:
            cat_id = get_or_create_categoria(conn, categoria, "gasto")
            campos.append("categoria_id = ?"); valores.append(cat_id)
        if not campos: return "❌ No se indicó ningún campo a modificar."
        valores.extend([id, user_id])
        cur = conn.execute(f"UPDATE productos SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
    return f"✅ Producto {id} actualizado." if cur.rowcount else f"❌ No encontré el producto ID {id}."


@tool
def quitar_producto_despensa(id: int) -> str:
    """Desactiva un producto de la despensa por su ID. No lo elimina permanentemente.
    Úsala cuando el usuario ya no quiera ver un producto en su despensa.

    Args:
        id: ID del producto a desactivar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        row = conn.execute("SELECT nombre FROM productos WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
        if not row: return f"❌ No encontré el producto ID {id}."
        conn.execute("UPDATE productos SET activo = 0 WHERE id = ? AND user_id = ?", (id, user_id))
    return f"✅ '{row['nombre']}' quitado de tu despensa."


# ── Compras ───────────────────────────────────────────────────────────────────

@tool
def registrar_compra_despensa(producto: str, precio: Optional[float] = None, cantidad: float = 1, tienda: Optional[str] = None, fecha: Optional[str] = None) -> str:
    """Registra que el usuario compró un producto de su despensa.
    Úsala cuando el usuario diga que fue al súper, a Costco, o que compró algo de su despensa.
    El producto debe existir en el catálogo.

    Args:
        producto: Nombre del producto (búsqueda parcial, ej: 'Persil', 'Leche')
        precio: Precio pagado (opcional)
        cantidad: Cantidad comprada (default 1)
        tienda: Tienda donde se compró
        fecha: Fecha YYYY-MM-DD; usa hoy si no se menciona
    """
    user_id = get_user_id()
    ARTICULOS = {"el", "la", "los", "las", "un", "una", "del", "al"}
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, nombre FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1 LIMIT 1",
            (user_id, f"%{producto}%"),
        ).fetchone()
        if not row:
            for palabra in [p for p in producto.split() if len(p) > 2 and p.lower() not in ARTICULOS]:
                row = conn.execute(
                    "SELECT id, nombre FROM productos WHERE user_id = ? AND nombre LIKE ? AND activo = 1 LIMIT 1",
                    (user_id, f"%{palabra}%"),
                ).fetchone()
                if row: break
        if not row:
            return f"⚠️ '{producto}' no está en tu despensa. Agrégalo primero."
        conn.execute(
            "INSERT INTO compras_despensa (producto_id, user_id, fecha, precio, cantidad, tienda, fuente) VALUES (?,?,?,?,?,?,'manual')",
            (row["id"], user_id, fecha or _hoy(), precio, cantidad, tienda),
        )
        _recalcular_patron(conn, row["id"])
    precio_str = f"${precio:.2f}" if precio else "sin precio"
    return f"✅ Compra registrada: {row['nombre']} x{cantidad} {precio_str}"


@tool
def listar_compras_despensa(producto: Optional[str] = None, desde: Optional[str] = None, hasta: Optional[str] = None) -> str:
    """Lista el historial de compras de despensa. Sin filtros muestra las últimas 30.

    Args:
        producto: Filtrar por nombre de producto (opcional)
        desde: Fecha inicio YYYY-MM-DD (opcional)
        hasta: Fecha fin YYYY-MM-DD (opcional)
    """
    user_id = get_user_id()
    query = """SELECT cd.id, p.nombre, cd.fecha, cd.precio, cd.cantidad, cd.tienda
               FROM compras_despensa cd JOIN productos p ON cd.producto_id = p.id
               WHERE cd.user_id = ?"""
    params = [user_id]
    if producto: query += " AND p.nombre LIKE ?"; params.append(f"%{producto}%")
    if desde: query += " AND cd.fecha >= ?"; params.append(desde)
    if hasta: query += " AND cd.fecha <= ?"; params.append(hasta)
    query += " ORDER BY cd.fecha DESC LIMIT 30"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    if not rows:
        return "ℹ️ No hay compras de despensa registradas."
    lines = [
        f"ID:{r['id']} {r['fecha']} | {r['nombre']} | " +
        (f"${r['precio']:.2f}" if r['precio'] else "—") +
        f" x{r['cantidad']} | {r['tienda'] or '—'}"
        for r in rows
    ]
    return f"📋 Compras de despensa ({len(rows)}):\n" + "\n".join(lines)


@tool
def editar_compra_despensa(id: int, precio: Optional[float] = None, cantidad: Optional[float] = None, tienda: Optional[str] = None, fecha: Optional[str] = None) -> str:
    """Edita una compra de despensa por su ID.

    Args:
        id: ID de la compra
        precio: Nuevo precio (opcional)
        cantidad: Nueva cantidad (opcional)
        tienda: Nueva tienda (opcional)
        fecha: Nueva fecha YYYY-MM-DD (opcional)
    """
    user_id = get_user_id()
    campos, valores = [], []
    if precio is not None: campos.append("precio = ?"); valores.append(precio)
    if cantidad is not None: campos.append("cantidad = ?"); valores.append(cantidad)
    if tienda: campos.append("tienda = ?"); valores.append(tienda)
    if fecha: campos.append("fecha = ?"); valores.append(fecha)
    if not campos: return "❌ No se indicó ningún campo a modificar."
    valores.extend([id, user_id])
    with get_conn() as conn:
        row = conn.execute("SELECT producto_id FROM compras_despensa WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
        if not row: return f"❌ No encontré la compra ID {id}."
        conn.execute(f"UPDATE compras_despensa SET {', '.join(campos)} WHERE id = ? AND user_id = ?", valores)
        _recalcular_patron(conn, row["producto_id"])
    return f"✅ Compra {id} actualizada."


@tool
def eliminar_compra_despensa(id: int) -> str:
    """Elimina una compra de despensa por su ID y recalcula el patrón del producto.

    Args:
        id: ID de la compra a eliminar
    """
    user_id = get_user_id()
    with get_conn() as conn:
        row = conn.execute("SELECT producto_id FROM compras_despensa WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
        if not row: return f"❌ No encontré la compra ID {id}."
        conn.execute("DELETE FROM compras_despensa WHERE id = ? AND user_id = ?", (id, user_id))
        _recalcular_patron(conn, row["producto_id"])
    return f"🗑️ Compra {id} eliminada."


# ── Lista y predicción ────────────────────────────────────────────────────────

@tool
def generar_lista_despensa() -> str:
    """Genera la lista de compras de despensa basada en patrones de consumo.
    Muestra qué productos toca comprar pronto vs. cuáles tienen tiempo.
    Úsala cuando el usuario pregunte qué necesita comprar o pida su lista de despensa.
    """
    user_id = get_user_id()
    hoy = datetime.now()
    limite = (hoy + timedelta(days=7)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.nombre, p.tienda_pref, pd.frec_prom_dias, pd.ultima_compra, pd.proxima_estimada, pd.num_registros
               FROM productos p LEFT JOIN patrones_despensa pd ON p.id = pd.producto_id
               WHERE p.user_id = ? AND p.activo = 1 ORDER BY p.nombre""", (user_id,)
        ).fetchall()
    if not rows:
        return "ℹ️ No tienes productos en tu despensa. Agrega productos y registra compras para activar predicciones."
    con_patron = [r for r in rows if (r["num_registros"] or 0) >= 3]
    sin_datos = [r for r in rows if (r["num_registros"] or 0) < 3]
    if not con_patron:
        lines = [f"• {r['nombre']} | {r['tienda_pref'] or '—'} | {r['num_registros'] or 0} registros" for r in rows]
        return "🛒 Lista completa — sin predicciones aún\n_(Necesito 3+ compras por producto para predecir)\n\n" + "\n".join(lines)
    toca = [r for r in con_patron if r["proxima_estimada"] and r["proxima_estimada"] <= limite]
    pronto = [r for r in con_patron if r["proxima_estimada"] and r["proxima_estimada"] > limite]
    respuesta = f"🛒 Lista de despensa — {hoy.strftime('%d/%m/%Y')}\n"
    if toca:
        lines = []
        for r in toca:
            dias = (datetime.strptime(r["proxima_estimada"], "%Y-%m-%d") - hoy).days
            urgencia = "⚠️ YA" if dias <= 0 else f"en {dias}d"
            lines.append(f"• {r['nombre']} | {r['tienda_pref'] or '—'} | {urgencia}")
        respuesta += f"\n🔴 Comprar ahora ({len(toca)}):\n" + "\n".join(lines)
    else:
        respuesta += "\n✅ Todo al día."
    if pronto:
        lines = [f"• {r['nombre']} — en ~{(datetime.strptime(r['proxima_estimada'],'%Y-%m-%d')-hoy).days}d" for r in pronto]
        respuesta += f"\n\n🟡 Próximamente:\n" + "\n".join(lines)
    if sin_datos:
        respuesta += f"\n\n⚪ Sin patrón aún:\n" + "\n".join(f"• {r['nombre']} ({r['num_registros'] or 0} registros)" for r in sin_datos)
    return respuesta


@tool
def consultar_prediccion_despensa(producto: str) -> str:
    """Muestra cuándo vuelve a necesitarse un producto específico según su patrón de compra.
    Úsala cuando el usuario pregunte cuándo debe comprar un producto concreto.

    Args:
        producto: Nombre del producto (ej: 'Persil', 'Leche')
    """
    user_id = get_user_id()
    ARTICULOS = {"el", "la", "los", "las", "un", "una", "del", "al"}
    nombre_busqueda = " ".join(w for w in producto.split() if w.lower() not in ARTICULOS)
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.nombre, p.tienda_pref, pd.frec_prom_dias, pd.ultima_compra, pd.proxima_estimada, pd.num_registros
               FROM productos p LEFT JOIN patrones_despensa pd ON p.id = pd.producto_id
               WHERE p.user_id = ? AND p.nombre LIKE ? AND p.activo = 1 LIMIT 1""",
            (user_id, f"%{nombre_busqueda}%"),
        ).fetchone()
        if not row:
            for palabra in [p for p in nombre_busqueda.split() if len(p) > 2]:
                row = conn.execute(
                    """SELECT p.nombre, p.tienda_pref, pd.frec_prom_dias, pd.ultima_compra, pd.proxima_estimada, pd.num_registros
                       FROM productos p LEFT JOIN patrones_despensa pd ON p.id = pd.producto_id
                       WHERE p.user_id = ? AND p.nombre LIKE ? AND p.activo = 1 LIMIT 1""",
                    (user_id, f"%{palabra}%"),
                ).fetchone()
                if row: break
    if not row: return f"❌ No encontré '{producto}' en tu despensa."
    num = row["num_registros"] or 0
    if num < 3: return f"📊 {row['nombre']}: solo {num} registro(s). Necesito 3+ compras para predecir."
    dias_frec = int(row["frec_prom_dias"])
    dias_restantes = (datetime.strptime(row["proxima_estimada"], "%Y-%m-%d") - datetime.now()).days
    estado = "⚠️ Ya debería haberlo comprado" if dias_restantes < 0 else f"en {dias_restantes} días ({row['proxima_estimada']})"
    return (f"📊 Predicción — {row['nombre']}\n• Frecuencia: cada {dias_frec} días\n"
            f"• Última compra: {row['ultima_compra']}\n• Próxima: {estado}\n"
            f"• Tienda: {row['tienda_pref'] or '—'}\n• Basado en {num} compras")
