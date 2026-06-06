import re
from typing import Optional
from db import get_conn, upsert_usuario

# Saludos/modismos con que abrían las respuestas viejas. Se recortan del historial
# al cargarlo para que el modelo no los imite (Gemini copia el patrón del historial
# por encima de la instrucción del system prompt). No tocan la BD, solo lo que ve el LLM.
_APERTURAS = (r"qué onda|que onda|órale|orale|hola|qué tal|que tal|ándale|andale|hey|ey|"
              r"buenas|qué hubo|que hubo|uy|listo")
_SALUDO_INI = re.compile(r"^\s*¡\s*(?:" + _APERTURAS + r")[^!\n]*!\s*", re.IGNORECASE)


def _limpiar_saludo(texto: str) -> str:
    """Quita el saludo/modismo inicial de una respuesta del asistente, si lo hay."""
    nuevo = _SALUDO_INI.sub("", texto, count=1)
    return nuevo.lstrip() if nuevo.strip() else texto

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
    # Invertir para orden cronológico (más antiguo primero) y limpiar saludos viejos
    # de las respuestas del asistente para que el modelo no los imite.
    return [
        {"tipo": r["tipo"],
         "contenido": _limpiar_saludo(r["contenido"]) if r["tipo"] == "outbound" else r["contenido"]}
        for r in reversed(rows)
    ]


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
