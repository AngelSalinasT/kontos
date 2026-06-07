from contextvars import ContextVar
from typing import Optional

_user_id: ContextVar[str] = ContextVar("user_id", default="")
_username: ContextVar[str] = ContextVar("username", default="")
_imagen_path: ContextVar[Optional[str]] = ContextVar("imagen_path", default=None)
_es_voz: ContextVar[bool] = ContextVar("es_voz", default=False)
# True cuando el mensaje continúa una conversación reciente (sin saludar de nuevo);
# False cuando arranca una sesión tras un rato de inactividad.
_continua_sesion: ContextVar[bool] = ContextVar("continua_sesion", default=False)

# El bot es un proceso de larga duración: estos dicts (por user_id) sobreviven entre turnos.
# `_ultima_imagen` guarda la ruta de la última foto que mandó el usuario para poder
# re-procesarla en el turno siguiente (p. ej. tras pedirle que aclare si es ticket o banco).
# `_imagen_pendiente` marca que esa foto quedó SIN registrar esperando esa aclaración.
_ultima_imagen: dict[str, str] = {}
_imagen_pendiente: dict[str, bool] = {}


def set_user_context(user_id: str, username: str, imagen_path: Optional[str] = None,
                     es_voz: bool = False, continua_sesion: bool = False):
    _user_id.set(user_id)
    _username.set(username)
    _imagen_path.set(imagen_path)
    _es_voz.set(es_voz)
    _continua_sesion.set(continua_sesion)
    if imagen_path:
        _ultima_imagen[user_id] = imagen_path


def get_user_id() -> str:
    return _user_id.get()


def get_username() -> str:
    return _username.get()


def get_imagen_path() -> Optional[str]:
    return _imagen_path.get()


def get_es_voz() -> bool:
    return _es_voz.get()


def get_ultima_imagen() -> Optional[str]:
    """Ruta de la última foto del usuario actual (sobrevive entre turnos del proceso)."""
    return _ultima_imagen.get(_user_id.get())


def set_imagen_pendiente(pendiente: bool) -> None:
    """Marca/limpia que la última foto del usuario quedó esperando aclaración."""
    _imagen_pendiente[_user_id.get()] = pendiente


def get_imagen_pendiente() -> bool:
    return _imagen_pendiente.get(_user_id.get(), False)


def get_continua_sesion() -> bool:
    return _continua_sesion.get()
