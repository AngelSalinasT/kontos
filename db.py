import sqlite3
from contextlib import contextmanager
from datetime import datetime

DATABASE_NAME = 'gastos.db'


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                username TEXT,
                nombre TEXT,
                email TEXT,
                fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                tipo TEXT CHECK(tipo IN ('gasto', 'ingreso', 'general'))
            )
        ''')

        c.execute('''
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

        c.execute('''
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

        c.execute('''
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

        c.execute('''
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                categoria_id INTEGER,
                monto_limite REAL NOT NULL,
                periodo TEXT DEFAULT 'mensual',
                FOREIGN KEY (categoria_id) REFERENCES categorias(id),
                FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
            )
        ''')

        # ── NUEVAS TABLAS ─────────────────────────────────────────────────────

        c.execute('''
            CREATE TABLE IF NOT EXISTS historial_mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('inbound', 'outbound')),
                contenido TEXT NOT NULL,
                tg_message_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                categoria_id INTEGER,
                nombre TEXT NOT NULL,
                marca TEXT,
                unidad TEXT,
                precio_ref REAL,
                tienda_pref TEXT,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id),
                FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS tickets_ocr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fecha TEXT NOT NULL,
                tienda TEXT,
                total REAL,
                imagen_path TEXT,
                procesado INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios(user_id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS compras_despensa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                ticket_id INTEGER,
                fecha TEXT NOT NULL,
                precio REAL,
                cantidad REAL DEFAULT 1,
                tienda TEXT,
                fuente TEXT DEFAULT 'manual' CHECK(fuente IN ('manual', 'voz', 'ocr')),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (producto_id) REFERENCES productos(id),
                FOREIGN KEY (user_id) REFERENCES usuarios(user_id),
                FOREIGN KEY (ticket_id) REFERENCES tickets_ocr(id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS patrones_despensa (
                producto_id INTEGER PRIMARY KEY,
                frec_prom_dias REAL,
                ultima_compra TEXT,
                proxima_estimada TEXT,
                num_registros INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            )
        ''')


# ── Utilidades compartidas ────────────────────────────────────────────────────

def upsert_usuario(conn, user_id: str, username: str):
    conn.execute(
        "INSERT OR IGNORE INTO usuarios (user_id, username) VALUES (?, ?)",
        (user_id, username)
    )


def get_or_create_categoria(conn, nombre: str, tipo: str = 'gasto') -> int:
    nombre = nombre.capitalize()
    row = conn.execute("SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO categorias (nombre, tipo) VALUES (?, ?)", (nombre, tipo)
    )
    return cur.lastrowid


# ── Movimientos (compatibilidad con tools.py) ────────────────────────────────

def insertar_movimiento(user_id, username, fecha, concepto, monto, categoria_id, origen):
    try:
        fecha_obj = datetime.strptime(fecha, '%d %B %Y')
        fecha_db = fecha_obj.strftime('%Y-%m-%d')
    except ValueError:
        try:
            fecha_obj = datetime.strptime(fecha, '%d %B')
            fecha_db = fecha_obj.replace(year=datetime.now().year).strftime('%Y-%m-%d')
        except ValueError:
            fecha_db = datetime.now().strftime('%Y-%m-%d')

    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO movimientos (user_id, username, fecha, concepto, monto, categoria_id, origen)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, username, fecha_db, concepto, monto, categoria_id, origen)
        )


def total_quincenal(user_id, fecha_inicio, fecha_fin):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT SUM(monto) FROM movimientos WHERE user_id = ? AND fecha BETWEEN ? AND ?',
            (user_id, fecha_inicio, fecha_fin)
        ).fetchone()
    return row[0] if row[0] is not None else 0.0


init_db()
