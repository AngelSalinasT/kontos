"""Nodo de entrada: enruta el turno según el tipo de mensaje.

No transforma nada; solo decide la rama determinista. Las tres ramas
(texto / voz / foto) preparan el texto que verá el agente.
"""
from state import State


def route_por_tipo(state: State) -> str:
    """Devuelve el nombre de la rama según state['tipo']. Texto por defecto."""
    tipo = state.get("tipo", "texto")
    return {"voz": "transcribir", "foto": "extraer_imagen"}.get(tipo, "texto")
