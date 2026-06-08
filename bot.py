import os
import re
import html as _html
import logging
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from graph import graph
from nodes.historial import guardar_mensaje, cargar_historial, continua_sesion
from context import set_user_context

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx loguea cada request con la URL completa, lo que filtra el token del bot
# (https://api.telegram.org/bot<TOKEN>/...) al journal. Subir a WARNING lo evita.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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


# ── Formato Telegram ─────────────────────────────────────────────────────────
# Gemini escribe markdown (**negrita**, *cursiva*, `código`), que Telegram NO
# renderiza sin parse_mode. Lo convertimos al HTML que Telegram sí entiende.

_CODEBLOCK = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
_INLINECODE = re.compile(r"`([^`\n]+?)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", re.DOTALL)
_ITALIC_ALT = re.compile(r"(?<![_\w])_(?!\s)(.+?)(?<!\s)_(?![_\w])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)


def _telegram_html(text: str) -> str:
    """Convierte el markdown ligero del LLM al HTML que renderiza Telegram.

    Los bloques de código (``` y `código`) se extraen ANTES de aplicar negrita/
    cursiva: si no, un concepto con asterisco dentro de una tabla (p. ej.
    'Stripe *amazon', 'Pay pal*comisione') se interpretaría como cursiva y
    rompería la alineación. Se guardan con un centinela (bytes nulos, que no
    aparecen en texto de usuario) y se reinsertan al final."""
    stash: list[str] = []
    def _guardar(html: str) -> str:
        stash.append(html)
        return f"\x00{len(stash) - 1}\x00"

    # 1) Extraer bloques de código del texto CRUDO, ANTES que nada: así el regex de
    #    encabezados (#) no se come una '# ' que sea contenido de la tabla, y la
    #    negrita/cursiva tampoco tocan asteriscos de adentro (p. ej. 'Stripe *amazon').
    text = _CODEBLOCK.sub(
        lambda m: _guardar(f"<pre>{_html.escape(m.group(1).strip(chr(10)), quote=False)}</pre>"), text)
    text = _INLINECODE.sub(
        lambda m: _guardar(f"<code>{_html.escape(m.group(1), quote=False)}</code>"), text)

    # 2) Ya sin bloques: quitar encabezados markdown, escapar y emfatizar.
    text = _HEADING.sub("", text)
    text = _html.escape(text, quote=False)         # protege & < >
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BOLD_ALT.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _ITALIC_ALT.sub(r"<i>\1</i>", text)

    # 3) Reinsertar los bloques ya formateados.
    for i, html in enumerate(stash):
        text = text.replace(f"\x00{i}\x00", html)
    return text


async def _responder(message, texto: str):
    """Envía con formato HTML; si el HTML quedara inválido, manda texto plano."""
    try:
        await message.reply_text(_telegram_html(texto), parse_mode=ParseMode.HTML)
    except BadRequest:
        await message.reply_text(texto)


def _build_state(user_id: str, username: str, text: str, imagen_path: str = None, es_voz: bool = False) -> dict:
    from langchain_core.messages import AIMessage
    historial = cargar_historial(user_id, limite=20)
    mensajes_previos = [
        HumanMessage(content=m["contenido"]) if m["tipo"] == "inbound"
        else AIMessage(content=m["contenido"])
        for m in historial
    ]
    set_user_context(
        user_id, username, imagen_path=imagen_path, es_voz=es_voz,
        continua_sesion=continua_sesion(user_id),
    )
    return {"messages": mensajes_previos + [HumanMessage(content=text)]}


async def _invocar_y_responder(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, user_id: str, texto_original: str):
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        result = graph.invoke(state)
        raw = result["messages"][-1].content
        if isinstance(raw, list):
            respuesta = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
        else:
            respuesta = raw

        guardar_mensaje(user_id, "inbound", texto_original, update.message.message_id)
        guardar_mensaje(user_id, "outbound", respuesta)

        await _responder(update.message, respuesta)
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
    await _invocar_y_responder(update, context, state, user_id, text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga audio de voz, transcribe con Whisper y procesa como texto."""
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    username = _display_name(user)

    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
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
        state = _build_state(user_id, username, texto, es_voz=True)
        await _invocar_y_responder(update, context, state, user_id, texto)

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

    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)

        # Ruta estable por usuario (una foto pendiente a la vez): NO se borra al terminar,
        # para poder re-procesarla en el siguiente turno si hay que pedir aclaración
        # (¿ticket o captura bancaria?). La próxima foto del usuario la sobreescribe.
        img_path = os.path.join(tempfile.gettempdir(), f"kontos_img_{user_id}.jpg")
        await tg_file.download_to_drive(img_path)

        caption = update.message.caption or "Te mando esta foto, regístrala donde corresponda."
        state = _build_state(user_id, username, caption, imagen_path=img_path)

        await _invocar_y_responder(update, context, state, user_id, "[foto de ticket]")

    except Exception as e:
        logger.error(f"Error procesando foto: {e}", exc_info=True)
        from telegram.error import TimedOut, NetworkError
        if isinstance(e, (TimedOut, NetworkError)):
            await update.message.reply_text("⏱️ Se me fue la señal al bajar la foto. Mándamela de nuevo, porfa.")
        else:
            await update.message.reply_text("❌ No pude procesar la imagen. Intenta con otra foto.")


# ── Error handler global ────────────────────────────────────────────────────────

async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Captura cualquier excepción no manejada para no spamear tracebacks crudos."""
    err = context.error
    logger.error("Excepción no manejada: %s", err, exc_info=err)
    # Si fue un timeout de red, avísale al usuario con algo accionable.
    if isinstance(update, Update) and update.effective_message:
        from telegram.error import TimedOut, NetworkError
        if isinstance(err, (TimedOut, NetworkError)):
            try:
                await update.effective_message.reply_text(
                    "⏱️ Se me fue la señal un momento. Vuelve a enviármelo, por favor."
                )
            except Exception:
                pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en .env")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        # Timeouts generosos: get_file/descargas de fotos se cortaban con el default (~5s).
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
        .media_write_timeout(60)
        .pool_timeout(15)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(_on_error)

    if ALLOWED_IDS:
        logger.info(f"🔒 Acceso restringido a: {ALLOWED_IDS}")
    else:
        logger.warning("⚠️  ALLOWED_USER_IDS vacío — nadie puede acceder al bot")
    logger.info("🤖 Kontos bot escuchando...")
    app.run_polling()


if __name__ == "__main__":
    main()
