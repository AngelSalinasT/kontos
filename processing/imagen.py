"""Extracción determinista de datos financieros desde una imagen.

Corre SIEMPRE al recibir una foto (no la decide el agente): manda la imagen al
modelo de visión y devuelve datos estructurados (tipo, movimientos, productos…).
No toca la base de datos: registrar es responsabilidad de las tools, que el
agente elige según el tipo. Si la visión falla, cae a OCR local (easyocr/tesseract).
"""
import os
import base64
import logging
from datetime import datetime
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_MIME = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def _data_uri(imagen_path: str) -> str:
    with open(imagen_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = _MIME.get(os.path.splitext(imagen_path)[1].lower(), "image/jpeg")
    return f"data:{mime};base64,{b64}"


def _ocr_texto(imagen_path: str) -> str:
    """Respaldo: extrae texto con OCR cuando la visión del modelo no está disponible."""
    try:
        import easyocr
        reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
        return "\n".join(reader.readtext(imagen_path, detail=0))
    except ImportError:
        pass
    try:
        from PIL import Image
        import pytesseract
        return pytesseract.image_to_string(Image.open(imagen_path), lang="spa")
    except Exception as e:
        return f"ERROR_OCR: {e}"


def _instrucciones(nombres_catalogo: list[str]) -> str:
    hoy = datetime.now().strftime("%Y-%m-%d")
    anio = hoy[:4]
    return f"""Eres un extractor de datos financieros. HOY es {hoy} (año actual: {anio}).
Las capturas de banco/tarjeta casi siempre muestran SOLO día y mes, SIN año. Cuando falte el año,
NO lo inventes ni uses años viejos: usa el año actual ({anio}). Solo si esa fecha quedara en
el FUTURO respecto a hoy ({hoy}) — p. ej. un movimiento de diciembre estando hoy en junio — usa el
año anterior ({int(anio) - 1}). Si una fila no trae fecha, usa {hoy}.

Analiza la imagen que envió el usuario y clasifícala:
- "ticket_compra": ticket/recibo de una TIENDA física (súper, farmacia, Costco…). Señales: nombre y dirección de la tienda, lista de PRODUCTOS con precio unitario, cantidades, subtotal/IVA/total, número de caja o folio.
- "estado_cuenta": captura de la app del banco o estado de cuenta con VARIOS movimientos/transacciones. Señales: renglones con fecha + concepto + monto, saldos, nombres de comercios (no productos), "pago con tarjeta", "compra", referencias.
- "gasto_suelto": comprobante de UN solo pago/cargo (transferencia, recibo de servicio, una compra individual).
- "desconocido": no se puede determinar o no es financiero.

Catálogo de despensa del usuario (mapea productos SOLO si es ticket_compra): {nombres_catalogo}

Responde SOLO con JSON válido, sin texto adicional:
{{"tipo": "ticket_compra|estado_cuenta|gasto_suelto|desconocido",
  "confianza": "alta|baja (usa 'baja' si dudas entre ticket_compra y estado_cuenta)",
  "tienda": "nombre de la tienda o null",
  "fecha": "YYYY-MM-DD (usa {hoy} si no aparece)",
  "total": <número o null: total del ticket_compra>,
  "productos": [{{"nombre_catalogo": "nombre EXACTO del catálogo si coincide, si no null", "nombre_ticket": "como aparece", "precio": <número o null>, "cantidad": <número>}}],
  "movimientos": [{{"concepto": "descripción del cargo", "monto": <número positivo>, "fecha": "YYYY-MM-DD (completa el año según la regla de HOY de arriba)", "categoria": "Comida|Transporte|Entretenimiento|Servicios|Salud|Compras|General"}}]}}

Reglas IMPORTANTES:
- Es una captura de movimientos bancarios/tarjeta: casi todo son GASTOS del usuario. Extrae TODOS los renglones que sean un cargo/compra; NO te saltes ninguno.
- "Pago con tarjeta", "compra con tarjeta", "cargo" = el usuario GASTÓ dinero → SÍ va en 'movimientos'.
- Excluye ÚNICAMENTE entradas de dinero a favor del usuario: pagos/abonos A la tarjeta de crédito, depósitos, transferencias recibidas, reembolsos e intereses a favor.
- 'productos' solo para ticket_compra; 'movimientos' solo para estado_cuenta o gasto_suelto.
- Si un monto no se ve con claridad, déjalo igualmente como movimiento con tu mejor lectura; no lo descartes por dudar."""


def extraer(imagen_path: str, nombres_catalogo: list[str]) -> dict | None:
    """Devuelve los datos financieros estructurados de la imagen, o None si no se pudo leer.

    Args:
        imagen_path: ruta local de la imagen.
        nombres_catalogo: nombres de productos de la despensa del usuario (para mapear tickets).
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from utils.json_parser import parse_json_from_text

    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
    )
    instrucciones = _instrucciones(nombres_catalogo)

    # 1) Visión directa sobre la imagen.
    try:
        msg = HumanMessage(content=[
            {"type": "text", "text": instrucciones},
            {"type": "image_url", "image_url": _data_uri(imagen_path)},
        ])
        raw = llm.invoke([msg]).content
        data = parse_json_from_text(raw if isinstance(raw, str) else str(raw))
        if data:
            logger.info("Imagen extraída vía visión.")
            return data
    except Exception as e:
        logger.warning("Visión falló (%s); intento OCR de respaldo.", e)

    # 2) Respaldo: OCR a texto y se lo pasamos al modelo como texto plano.
    texto = _ocr_texto(imagen_path)
    if texto.startswith("ERROR_OCR"):
        logger.error("Fallo OCR: %s", texto)
        return None
    logger.info("OCR imagen (%d chars): %s", len(texto), texto[:200].replace("\n", " | "))
    try:
        raw = llm.invoke(f"{instrucciones}\n\nTexto OCR de la imagen:\n---\n{texto[:3500]}\n---").content
        data = parse_json_from_text(raw if isinstance(raw, str) else str(raw))
        if data:
            logger.info("Imagen extraída vía OCR.")
        return data
    except Exception as e:
        logger.error("No se pudo extraer datos de la imagen ni por OCR: %s", e)
        return None
