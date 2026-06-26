"""Transcripción de notas de voz con faster-whisper (CPU, modelo configurable).

Convierte el OGG/OGA de Telegram a WAV antes de transcribir. Usa ffmpeg directo
para la conversión: en Python 3.13+ `pydub` está roto (se eliminó `audioop` de la
stdlib), así que no dependemos de él.
"""
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# El modelo de Whisper se carga una sola vez y se reutiliza (singleton).
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        logger.info("Cargando Whisper modelo '%s' en CPU...", model_size)
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper listo.")
    return _model


def _a_wav(origen: str) -> str:
    """Convierte un audio a WAV 16kHz mono con ffmpeg y devuelve la ruta del WAV."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        destino = tmp.name
    código = os.system(f'ffmpeg -y -i "{origen}" -ar 16000 -ac 1 "{destino}" -loglevel quiet')
    if código != 0:
        logger.warning("ffmpeg devolvió código %s al convertir %s", código, origen)
    return destino


def transcribir(audio_path: str) -> str:
    """Transcribe un audio (OGG/OGA/MP3/WAV) y devuelve el texto en español, o "" si falla."""
    wav_path = None
    try:
        wav_path = audio_path if audio_path.endswith(".wav") else _a_wav(audio_path)
        segments, _ = _get_model().transcribe(wav_path, language="es", beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        logger.error("Error en transcripción Whisper: %s", e)
        return ""
    finally:
        if wav_path and wav_path != audio_path and os.path.exists(wav_path):
            os.remove(wav_path)
