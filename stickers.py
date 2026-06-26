"""Stickers de gatos para que Kontos se exprese como en WhatsApp.

El agente decide CUÁNDO mandar uno (marca su respuesta con [[sticker:VIBE]]); aquí
resolvemos la VIBE a un pack de la comunidad y devolvemos un file_id al azar. Los
file_id se obtienen con getStickerSet (packs públicos) y se cachean en memoria; no
se hostea nada. Si un pack no carga, simplemente no se manda sticker.
"""
import os
import json
import random
import logging
import urllib.request

logger = logging.getLogger(__name__)

# vibe → packs (short_names de t.me/addstickers/...). Hoy son gatos meme en tendencia;
# al sumar más packs se afina el mapeo por estado de ánimo.
VIBES: dict[str, list[str]] = {
    "festejo": ["stellarcats", "cats_memes_tiktok"],
    "alerta":  ["cats_memes_tiktok", "stellarcats"],
    "saludo":  ["stellarcats", "cats_memes_tiktok"],
    "random":  ["cats_memes_tiktok", "stellarcats"],
}
_DEFAULT_PACKS = ["cats_memes_tiktok", "stellarcats"]

_cache: dict[str, list[str]] = {}  # pack short_name -> [file_id]


def _file_ids(pack: str) -> list[str]:
    """file_ids de un pack (cacheados). Carga perezosa vía getStickerSet."""
    if pack not in _cache:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        try:
            url = f"https://api.telegram.org/bot{token}/getStickerSet?name={pack}"
            d = json.load(urllib.request.urlopen(url, timeout=10))
            _cache[pack] = [s["file_id"] for s in d["result"]["stickers"]] if d.get("ok") else []
            logger.info("Sticker pack '%s': %d stickers cargados.", pack, len(_cache[pack]))
        except Exception as e:
            logger.warning("No pude cargar el sticker pack '%s': %s", pack, e)
            _cache[pack] = []
    return _cache[pack]


def sticker_para(vibe: str) -> str | None:
    """Devuelve un file_id de sticker al azar para la vibe dada, o None si no hay."""
    packs = VIBES.get((vibe or "").lower().strip(), _DEFAULT_PACKS)
    pool = [fid for p in packs for fid in _file_ids(p)]
    return random.choice(pool) if pool else None
