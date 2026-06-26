"""Rama de texto: el mensaje ya es texto, se entrega tal cual al agente."""
from langchain_core.messages import HumanMessage
from state import State


def texto_node(state: State) -> dict:
    texto = (state.get("texto") or "").strip()
    return {"messages": [HumanMessage(content=texto)], "texto_original": texto}
