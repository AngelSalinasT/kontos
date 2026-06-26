"""Estado compartido del grafo de Kontos.

Un solo TypedDict que viaja por todos los nodos. `messages` es la conversación
(historial + turno actual); el resto son metadatos del turno que ponen los
handlers de Telegram (bot.py) y consumen los nodos de entrada del grafo.
"""
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict, total=False):
    # Conversación. El reducer add_messages acumula los mensajes que cada nodo agrega.
    messages: Annotated[list, add_messages]
    # Tipo del mensaje entrante: decide la rama determinista de entrada.
    tipo: str  # "texto" | "voz" | "foto"
    # Insumos crudos según el tipo (los pone bot.py; los consumen los nodos).
    texto: Optional[str]        # texto tal cual (rama "texto")
    audio_path: Optional[str]   # ruta del audio a transcribir (rama "voz")
    imagen_path: Optional[str]  # ruta de la imagen a extraer (rama "foto")
    caption: Optional[str]      # texto que acompaña a la foto, si lo hay
    # Texto resuelto del turno para persistir en el historial (lo fija el nodo de entrada).
    texto_original: Optional[str]
