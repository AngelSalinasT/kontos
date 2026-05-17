"""
Carga los productos iniciales de la despensa de Angel basados en el ticket
de Costco Querétaro del 08/sep/2025 y el historial de compras conocido.

Uso: python3 seed.py <tu_telegram_user_id>
     python3 seed.py  (usa user_id de .env o "angel" por defecto)
"""
import sys
import os
from dotenv import load_dotenv
from db import get_conn, init_db, upsert_usuario, get_or_create_categoria

load_dotenv()

PRODUCTOS = [
    # (nombre, marca, categoria, unidad, precio_ref, tienda_pref)
    ("Leche Deslactosada UHT",  "Kirkland",  "Despensa",  "caja 12L", 428.13,  "Costco"),   # 856.26 / 2
    ("Pañales Tena Slip MDN",   "Tena",      "Higiene",   "paquete 60pz", 660.55, "Costco"),
    ("Persil Líquido",          "Persil",    "Limpieza",  "botella 10L",  369.54, "Costco"),
    ("Suavizante Downy",        "Downy",     "Limpieza",  "botella gde",  281.35, "Costco"),
    ("Aceite Nutrioli",         "Nutrioli",  "Despensa",  "pack 3x946ml", 325.44, "Costco"),
    ("Papel Higiénico",         "Kirkland",  "Higiene",   "paquete",      413.61, "Costco"),
    ("Atún en Agua",            "Dolores",   "Despensa",  "pack 10x140g", 193.35, "Costco"),
    ("Desodorante Rexona",      "Rexona",    "Higiene",   "pack 5pz",     237.23, "Costco"),
    ("Bolsas de Basura",        "Kirkland",  "Hogar",     "paquete 147L", 127.87, "Costco"),
    ("Jabón Palmolive",         "Palmolive", "Higiene",   "multipack",    None,   "Costco"),
    ("Nescafé Clásico",         "Nescafé",   "Despensa",  "bote grande",  None,   "Costco"),
    ("Chocomilk",               "Nestlé",    "Despensa",  "bote grande",  None,   "Costco"),
    ("Cereal Kornflakes",       "Kellogg's", "Despensa",  "bolsa 1kg",    120.0,  "Costco"),
    ("Cereal Sucaritas",        "Kellogg's", "Despensa",  "bolsa 1kg",    120.0,  "Costco"),
    ("Saba Ultra",              "Saba",      "Higiene",   "pack 80pz",    224.04, "Costco"),
    # La Ahorrera
    ("Shampoo",                 None,        "Higiene",   "botella",      None,   "La Ahorrera"),
    ("Navajas de Rasurar",      None,        "Higiene",   "paquete",      None,   "La Ahorrera"),
    ("Especias Nord Suiza",     "Nord Suiza","Despensa",  "sobre",        None,   "La Ahorrera"),
]


def seed(user_id: str, username: str = "angel"):
    init_db()
    with get_conn() as conn:
        upsert_usuario(conn, user_id, username)
        insertados = 0
        for nombre, marca, categoria, unidad, precio_ref, tienda in PRODUCTOS:
            # Evitar duplicados
            existe = conn.execute(
                "SELECT id FROM productos WHERE user_id = ? AND nombre = ?",
                (user_id, nombre)
            ).fetchone()
            if existe:
                print(f"  ⏭  Ya existe: {nombre}")
                continue
            cat_id = get_or_create_categoria(conn, categoria, "gasto")
            conn.execute(
                '''INSERT INTO productos (user_id, categoria_id, nombre, marca, unidad, precio_ref, tienda_pref)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (user_id, cat_id, nombre, marca, unidad, precio_ref, tienda)
            )
            print(f"  ✅ {nombre} ({tienda}) ${precio_ref or '—'}")
            insertados += 1

    print(f"\n✓ {insertados} productos cargados para user_id='{user_id}'")


if __name__ == "__main__":
    uid = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SEED_USER_ID", "angel")
    uname = sys.argv[2] if len(sys.argv) > 2 else "Angel"
    print(f"🌱 Cargando productos para user_id='{uid}'...\n")
    seed(uid, uname)
