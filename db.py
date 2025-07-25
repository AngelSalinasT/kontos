# db.py
import sqlite3
from datetime import datetime

DATABASE_NAME = 'gastos.db'

def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # Tabla de categorías
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT CHECK(tipo IN ('gasto', 'ingreso'))
        )
    ''')
    # Tabla de gastos fijos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            categoria_id INTEGER,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha_inicio TEXT,
            periodicidad TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
        )
    ''')
    # Tabla de ingresos fijos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingresos_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            categoria_id INTEGER,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha_inicio TEXT,
            periodicidad TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
        )
    ''')
    # Tabla de presupuestos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS presupuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            categoria_id INTEGER,
            monto_limite REAL NOT NULL,
            periodo TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
        )
    ''')
    # Tabla de movimientos (actualizada para usar categoria_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT,
            fecha TEXT NOT NULL,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            categoria_id INTEGER,
            origen TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
        )
    ''')
    # Tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE,  -- Puede ser un identificador externo (Telegram, email, etc.)
            username TEXT,
            nombre TEXT,
            email TEXT,
            fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    conn.close()

def insertar_movimiento(user_id, username, fecha, concepto, monto, categoria_id, origen):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # === MEJORA: Convertir la fecha a YYYY-MM-DD antes de insertar ===
    # La fecha que viene de save_to_db_node ahora debería ser "DD Mes YYYY"
    try:
        fecha_obj = datetime.strptime(fecha, '%d %B %Y')
        fecha_db_format = fecha_obj.strftime('%Y-%m-%d')
    except ValueError:
        print(f"Advertencia: Formato de fecha inesperado para DB: '{fecha}'. Intentando parsear con otros formatos.")
        try: # Intentar con "DD Mes" y añadir el año actual si no viene
            fecha_obj = datetime.strptime(fecha, '%d %B')
            fecha_obj = fecha_obj.replace(year=datetime.now().year)
            fecha_db_format = fecha_obj.strftime('%Y-%m-%d')
        except ValueError:
            print(f"Error: No se pudo parsear la fecha '{fecha}'. Usando fecha actual para DB.")
            fecha_db_format = datetime.now().strftime('%Y-%m-%d')
            
    cursor.execute('''
        INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, fecha_db_format, concepto, monto, categoria_id, origen))
    conn.commit()
    conn.close()
    print(f"DB: Movimiento insertado: {concepto} - {monto} (Fecha DB: {fecha_db_format})")

def total_quincenal(user_id, fecha_inicio, fecha_fin):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(monto) FROM movimientos
        WHERE user_id = ? AND fecha BETWEEN ? AND ?
    ''', (user_id, fecha_inicio, fecha_fin))
    total = cursor.fetchone()[0]
    conn.close()
    print(f"DB: Total consultado para user_id={user_id} del {fecha_inicio} al {fecha_fin}: {total}")
    return total if total is not None else 0.0

init_db()
