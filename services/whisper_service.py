"""
Transcripción de audio con faster-whisper (CPU, modelo tiny).
Convierte OGG/OGA de Telegram a WAV antes de transcribir.
"""
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# Modelo cargado una sola vez (singleton)
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        logger.info(f"Cargando Whisper modelo '{model_size}' en CPU...")
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper listo.")
    return _model


def _convertir_a_wav(origen: str, destino: str):
    """Convierte audio OGG/OGA/MP3 a WAV usando pydub."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(origen)
        audio.export(destino, format="wav")
    except ImportError:
        # Fallback: ffmpeg directo si pydub no está
        os.system(f'ffmpeg -y -i "{origen}" -ar 16000 -ac 1 "{destino}" -loglevel quiet')


def transcribir(audio_path: str) -> str:
    """
    Transcribe un archivo de audio y devuelve el texto en español.
    Acepta OGG, OGA, MP3, WAV.
    """
    try:
        # Convertir a WAV si no es WAV
        if not audio_path.endswith(".wav"):
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            _convertir_a_wav(audio_path, wav_path)
        else:
            wav_path = audio_path

        model = _get_model()
        segments, _ = model.transcribe(wav_path, language="es", beam_size=1)
        texto = " ".join(seg.text for seg in segments).strip()

        # Limpiar tmp
        if wav_path != audio_path and os.path.exists(wav_path):
            os.remove(wav_path)

        return texto or ""
    except Exception as e:
        logger.error(f"Error en transcripción Whisper: {e}")
        return ""
