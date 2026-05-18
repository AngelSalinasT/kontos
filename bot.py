import os
import logging
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from graph import graph
from nodes.historial import guardar_mensaje, cargar_historial

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# IDs de Telegram autorizados — separados por coma en ALLOWED_USER_IDS
# Si la variable está vacía, el bot rechaza a todo el mundo salvo el owner
_raw_allowed = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_IDS: set[str] = {uid.strip() for uid in _raw_allowed.split(",") if uid.strip()}


def _autorizado(user_id: str) -> bool:
    return user_id in ALLOWED_IDS


async def _rechazar(update: Update):
    logger.warning(f"Acceso denegado a user_id={update.effective_user.id}")
    await update.message.reply_text("⛔ No tienes acceso a este bot.")


def _display_name(user) -> str:
    return user.username or user.first_name or f"Usuario_{user.id}"


def _build_state(user_id: str, username: str, text: str, **extra) -> dict:
    """Construye el estado inicial para el grafo incluyendo historial."""
    historial = cargar_historial(user_id, limite=20)
    mensajes_previos = []
    for msg in historial:
        from langchain_core.messages import AIMessage
        if msg["tipo"] == "inbound":
            mensajes_previos.append(HumanMessage(content=msg["contenido"]))
        else:
            mensajes_previos.append(AIMessage(content=msg["contenido"]))

    return {
        "messages": mensajes_previos + [HumanMessage(content=text)],
        "user_id": user_id,
        "username": username,
        **extra,
    }


async def _invocar_y_responder(update: Update, state: dict, user_id: str, texto_original: str):
    """Invoca el grafo, persiste mensajes y responde al usuario."""
    try:
        result = graph.invoke(state)
        respuesta = result.get("final_response") or "❌ No pude procesar tu solicitud."

        # Persistir inbound + outbound
        guardar_mensaje(user_id, "inbound", texto_original, update.message.message_id)
        guardar_mensaje(user_id, "outbound", respuesta)

        await update.message.reply_text(respuesta)
    except Exception as e:
        logger.error(f"Error invocando grafo: {e}", exc_info=True)
        await update.message.reply_text("❌ Error interno. Intenta de nuevo.")


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _autorizado(str(user.id)):
        await _rechazar(update); return
    nombre = user.first_name or "amigo"
    await update.message.reply_text(
        f"👋 Hola {nombre}! Soy Kontos, tu asistente de finanzas y despensa.\n\n"
        "Puedo ayudarte a:\n"
        "• Registrar gastos y compras\n"
        "• Gestionar tu despensa y predecir cuándo comprar\n"
        "• Escanear tickets con fotos\n"
        "• Enviar notas de voz\n"
        "• Consultar totales y presupuestos\n\n"
        "Escribe o manda un audio. ¿En qué te ayudo?"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    username = _display_name(user)
    text = update.message.text.strip()

    logger.info(f"TEXT {username}({user_id}): {text}")
    state = _build_state(user_id, username, text)
    await _invocar_y_responder(update, state, user_id, text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga audio de voz, transcribe con Whisper y procesa como texto."""
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    username = _display_name(user)

    await update.message.reply_text("🎙️ Transcribiendo tu audio...")

    try:
        from services.whisper_service import transcribir
        voice = update.message.voice or update.message.audio
        tg_file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as tmp:
            audio_path = tmp.name
        await tg_file.download_to_drive(audio_path)

        texto = transcribir(audio_path)
        os.remove(audio_path)

        if not texto:
            await update.message.reply_text("❌ No pude entender el audio. Intenta de nuevo o escribe el mensaje.")
            return

        logger.info(f"VOICE {username}({user_id}) → '{texto}'")
        await update.message.reply_text(f"📝 Entendí: _{texto}_", parse_mode="Markdown")

        state = _build_state(user_id, username, texto, es_voz=True)
        await _invocar_y_responder(update, state, user_id, texto)

    except ImportError:
        await update.message.reply_text(
            "⚠️ Whisper no está instalado. Instala faster-whisper:\n`pip install faster-whisper pydub`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error procesando voz: {e}", exc_info=True)
        await update.message.reply_text("❌ Error procesando el audio.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga foto de ticket y la pasa al nodo procesar_ticket."""
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    username = _display_name(user)

    await update.message.reply_text("🧾 Procesando ticket...")

    try:
        # La foto más grande (mejor calidad)
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img_path = tmp.name
        await tg_file.download_to_drive(img_path)

        caption = update.message.caption or "procesar ticket"
        state = _build_state(user_id, username, caption, imagen_path=img_path)
        # Forzar la decisión al nodo de ticket
        state["decision"] = "procesar_ticket"

        await _invocar_y_responder(update, state, user_id, "[foto de ticket]")
        os.remove(img_path)

    except Exception as e:
        logger.error(f"Error procesando foto: {e}", exc_info=True)
        await update.message.reply_text("❌ Error procesando la imagen del ticket.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en .env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    if ALLOWED_IDS:
        logger.info(f"🔒 Acceso restringido a: {ALLOWED_IDS}")
    else:
        logger.warning("⚠️  ALLOWED_USER_IDS vacío — nadie puede acceder al bot")
    logger.info("🤖 Kontos bot escuchando...")
    app.run_polling()


if __name__ == "__main__":
    main()
