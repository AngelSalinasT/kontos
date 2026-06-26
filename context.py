"""Contexto del turno actual (por usuario), accesible desde nodos y herramientas.

Se apoya en ContextVar para los datos del turno (user_id, username, tono de sesión)
y en dicts por user_id para lo que debe sobrevivir entre turnos del proceso de larga
duración: la última foto y sus datos extraídos, pendientes de aclarar/registrar.
"""
from contextvars import ContextVar
from typing import Optional

_user_id: ContextVar[str] = ContextVar("user_id", default="")
_username: ContextVar[str] = ContextVar("username", default="")
# True cuando el mensaje continúa una conversación reciente (sin saludar de nuevo).
_continua_sesion: ContextVar[bool] = ContextVar("continua_sesion", default=False)

# Sobreviven entre turnos (el bot es un proceso de larga duración):
# datos financieros extraídos de la última foto, esperando que el agente la clasifique
# (ticket vs banco) cuando la extracción fue ambigua; y el flag de "pendiente".
_datos_imagen: dict[str, dict] = {}
_imagen_pendiente: dict[str, bool] = {}


def set_user_context(user_id: str, username: str, continua_sesion: bool = False):
    _user_id.set(user_id)
    _username.set(username)
    _continua_sesion.set(continua_sesion)


def get_user_id() -> str:
    return _user_id.get()


def get_username() -> str:
    return _username.get()


def get_continua_sesion() -> bool:
    return _continua_sesion.get()


def set_datos_imagen(data: Optional[dict]) -> None:
    """Guarda (o limpia con None) los datos extraídos de la última foto del usuario."""
    uid = _user_id.get()
    if data is None:
        _datos_imagen.pop(uid, None)
    else:
        _datos_imagen[uid] = data


def get_datos_imagen() -> Optional[dict]:
    return _datos_imagen.get(_user_id.get())


def set_imagen_pendiente(pendiente: bool) -> None:
    _imagen_pendiente[_user_id.get()] = pendiente


def get_imagen_pendiente() -> bool:
    return _imagen_pendiente.get(_user_id.get(), False)
