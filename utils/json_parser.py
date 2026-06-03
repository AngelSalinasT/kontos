import json
import re
from typing import Any, Optional


def _extraer_balanceado(text: str, abre: str, cierra: str) -> Optional[str]:
    """Devuelve el primer fragmento balanceado entre `abre`/`cierra`, respetando
    anidación y comillas. Ignora llaves/corchetes dentro de strings JSON."""
    inicio = text.find(abre)
    if inicio == -1:
        return None
    profundidad = 0
    en_string = False
    escape = False
    for i in range(inicio, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            en_string = not en_string
            continue
        if en_string:
            continue
        if c == abre:
            profundidad += 1
        elif c == cierra:
            profundidad -= 1
            if profundidad == 0:
                return text[inicio:i + 1]
    return None


def parse_json_from_text(text: str) -> Optional[Any]:
    """Extrae JSON de texto crudo del LLM, tolerando markdown code blocks y
    objetos/arrays anidados envueltos en texto adicional."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extraer el primer objeto o array balanceado (soporta anidación).
    candidatos = [c for c in (
        _extraer_balanceado(text, '{', '}'),
        _extraer_balanceado(text, '[', ']'),
    ) if c]
    # Priorizar el que aparece primero en el texto.
    candidatos.sort(key=lambda c: text.find(c))
    for fragmento in candidatos:
        try:
            return json.loads(fragmento)
        except json.JSONDecodeError:
            continue
    return None
