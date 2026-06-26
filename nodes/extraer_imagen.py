"""Rama de foto: extrae los datos de la imagen y, si es claro, los registra —todo
determinista— y le entrega al agente un texto con el resultado para que lo comente.

El agente NO procesa la imagen: cuando llega aquí ya está extraída y (salvo caso
ambiguo) registrada. Solo si no se distingue ticket de captura bancaria se deja
pendiente y se le pide al agente que pregunte.
"""
import logging
from langchain_core.messages import HumanMessage
from state import State
from db import get_conn
from context import (
    get_user_id, get_username, set_datos_imagen, set_imagen_pendiente,
)
from processing.imagen import extraer
from tools.imagen import registrar_movimientos, registrar_ticket

logger = logging.getLogger(__name__)


def _msg(texto: str, original: str) -> dict:
    return {"messages": [HumanMessage(content=texto)], "texto_original": original}


def extraer_imagen_node(state: State) -> dict:
    user_id, username = get_user_id(), get_username()
    imagen_path = state.get("imagen_path")

    with get_conn() as conn:
        catalogo = conn.execute(
            "SELECT nombre FROM productos WHERE user_id = ? AND activo = 1", (user_id,)
        ).fetchall()
    nombres = [r["nombre"] for r in catalogo]

    data = extraer(imagen_path, nombres) if imagen_path else None
    if not data:
        return _msg("[Sistema] No se pudo leer la imagen que envió Ángel. Pídele una foto más "
                    "nítida.", "[foto ilegible]")

    tipo = (data.get("tipo") or "").lower()
    confianza = (data.get("confianza") or "alta").lower()

    # Ambiguo: no registramos; cacheamos y pedimos al agente que aclare con Ángel.
    if tipo == "desconocido" or confianza == "baja":
        set_datos_imagen(data)
        set_imagen_pendiente(True)
        tienda = data.get("tienda")
        pista = f" Parece de {tienda}." if tienda else ""
        return _msg(
            "[Sistema] Ángel envió una foto, pero la extracción no distingue con seguridad si es "
            f"un TICKET de compra (va a despensa) o una CAPTURA bancaria (va a gastos).{pista} "
            "Pregúntale en una línea cuál es; no se ha registrado nada aún.",
            "[foto: pendiente de aclarar]")

    # Claro: registramos de forma determinista y le pasamos el resultado al agente.
    set_datos_imagen(None)
    set_imagen_pendiente(False)
    if tipo == "ticket_compra":
        resumen = registrar_ticket(user_id, username, data)
        return _msg(
            "[Sistema] Ángel envió un TICKET de compra; ya se registró en la despensa "
            f"automáticamente. Resultado:\n{resumen}\n\nComéntaselo con naturalidad y brevedad.",
            "[ticket de compra]")

    # estado_cuenta / gasto_suelto → gastos
    resumen = registrar_movimientos(user_id, username, data)
    return _msg(
        "[Sistema] Ángel envió una CAPTURA bancaria; los gastos ya se registraron "
        f"automáticamente. Resultado:\n{resumen}\n\nConfírmaselo de forma conversacional y breve: "
        "no listes todos los montos salvo que convenga, y si con `resumen_financiero` detectas una "
        "alerta útil (presupuesto cerca del límite, ritmo de gasto alto, categoría disparada), "
        "menciónala.",
        "[captura bancaria]")
