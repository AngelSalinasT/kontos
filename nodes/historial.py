from typing import Optional
from db import get_conn, upsert_usuario


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
