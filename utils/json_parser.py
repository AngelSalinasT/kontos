import json
import re
from typing import Any, Optional


def parse_json_from_text(text: str) -> Optional[Any]:
    """Extrae JSON de texto crudo del LLM, tolerando markdown code blocks."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Intentar extraer array
    arr = re.search(r'\[.*\]', text, re.DOTALL)
    if arr:
        try:
            return json.loads(arr.group(0))
        except json.JSONDecodeError:
            pass
    # Intentar extraer objeto
    obj = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if obj:
        try:
            return json.loads(obj.group(0))
        except json.JSONDecodeError:
            pass
    return None
