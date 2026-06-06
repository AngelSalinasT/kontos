from typing import Optional
from db import get_conn, upsert_usuario

# Minutos de inactividad tras los cuales el siguiente mensaje se trata como una
# nueva sesión (el bot puede volver a saludar). Dentro de la ventana, continúa
# la conversación sin re-saludar.
VENTANA_SESION_MIN = 180


def guardar_mensaje(user_id: str, tipo: str, contenido: str, tg_message_id: Optional[int] = None):
    """Persiste un mensaje inbound o outbound en la DB."""
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO historial_mensajes (user_id, tipo, contenido, tg_message_id)
               VALUES (?, ?, ?, ?)''',
            (user_id, tipo, contenido, tg_message_id)
        )


def cargar_historial(user_id: str, limite: int = 20) -> list[dict]:
    """Carga los últimos N mensajes del usuario ordenados cronológicamente."""
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT tipo, contenido FROM historial_mensajes
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT ?''',
            (user_id, limite)
        ).fetchall()
    # Invertir para orden cronológico (más antiguo primero)
    return [{"tipo": r["tipo"], "contenido": r["contenido"]} for r in reversed(rows)]


def continua_sesion(user_id: str, ventana_min: int = VENTANA_SESION_MIN) -> bool:
    """True si el último mensaje del usuario es lo bastante reciente como para
    considerar que la conversación sigue en curso (y NO volver a saludar).

    La memoria durable son los últimos N mensajes en SQLite (siempre se cargan);
    esto solo decide el *tono de apertura*: continuar vs. arrancar de nuevo.
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT (julianday('now') - julianday(MAX(timestamp))) * 24 * 60 AS mins
               FROM historial_mensajes WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
    mins = row["mins"] if row else None
    return mins is not None and mins <= ventana_min
