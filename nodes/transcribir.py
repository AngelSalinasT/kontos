"""Rama de voz: transcribe el audio a texto y se lo entrega al agente como texto."""
import logging
from langchain_core.messages import HumanMessage
from state import State
from processing.audio import transcribir

logger = logging.getLogger(__name__)


def transcribir_node(state: State) -> dict:
    audio_path = state.get("audio_path")
    texto = transcribir(audio_path) if audio_path else ""
    if not texto:
        # Sin transcripción no hay nada que el agente pueda hacer: se lo decimos para
        # que le pida a Ángel reintentar, en vez de inventar.
        aviso = ("[Sistema] No se pudo entender el audio que envió Ángel. Pídele que lo repita "
                 "o que lo escriba.")
        return {"messages": [HumanMessage(content=aviso)], "texto_original": "[audio no entendido]"}
    logger.info("VOICE → '%s'", texto)
    return {"messages": [HumanMessage(content=texto)], "texto_original": texto}
