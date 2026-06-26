"""Nodo agente: un ReAct (LLM + tools) que conversa y decide qué herramientas usar.

Recibe el texto ya preprocesado por las ramas de entrada y produce la respuesta.
Se construye una sola vez (el modelo y las tools no cambian entre turnos).
"""
import os
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from tools import ALL_TOOLS
from agent.prompt import build_prompt
from state import State

_llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.3")),
)

_react = create_react_agent(model=_llm, tools=ALL_TOOLS, prompt=build_prompt)


def agente_node(state: State) -> dict:
    """Corre el ciclo ReAct sobre los mensajes y devuelve solo los mensajes nuevos
    (evita duplicar el historial al volver al reducer del grafo padre)."""
    previos = len(state["messages"])
    salida = _react.invoke({"messages": state["messages"]})
    return {"messages": salida["messages"][previos:]}
