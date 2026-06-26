import os
import re
import html as _html
import asyncio
import logging
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage, AIMessage
from graph import graph
from persistence.historial import guardar_mensaje, cargar_historial, continua_sesion
from context import set_user_context

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx loguea cada request con la URL completa, lo que filtra el token del bot al journal.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# IDs de Telegram autorizados (coma-separados en ALLOWED_USER_IDS). Vacío = nadie entra.
_raw_allowed = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_IDS: set[str] = {uid.strip() for uid in _raw_allowed.split(",") if uid.strip()}


def _autorizado(user_id: str) -> bool:
    return user_id in ALLOWED_IDS


async def _rechazar(update: Update):
    logger.warning("Acceso denegado a user_id=%s", update.effective_user.id)
    await update.message.reply_text("⛔ No tienes acceso a este bot.")


def _display_name(user) -> str:
    return user.username or user.first_name or f"Usuario_{user.id}"


# ── Formato Telegram ─────────────────────────────────────────────────────────
# Gemini escribe markdown (**negrita**, *cursiva*, `código`); lo pasamos al HTML de Telegram.
_CODEBLOCK = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
_INLINECODE = re.compile(r"`([^`\n]+?)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", re.DOTALL)
_ITALIC_ALT = re.compile(r"(?<![_\w])_(?!\s)(.+?)(?<!\s)_(?![_\w])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)


def _telegram_html(text: str) -> str:
    """Convierte el markdown ligero del LLM al HTML que renderiza Telegram.

    Los bloques de código (``` y `código`) se extraen ANTES de aplicar negrita/cursiva
    para que un asterisco dentro de una tabla no se interprete como cursiva y rompa la
    alineación. Se guardan con un centinela (bytes nulos) y se reinsertan al final."""
    stash: list[str] = []
    def _guardar(html: str) -> str:
        stash.append(html)
        return f"\x00{len(stash) - 1}\x00"

    text = _CODEBLOCK.sub(
        lambda m: _guardar(f"<pre>{_html.escape(m.group(1).strip(chr(10)), quote=False)}</pre>"), text)
    text = _INLINECODE.sub(
        lambda m: _guardar(f"<code>{_html.escape(m.group(1), quote=False)}</code>"), text)

    text = _HEADING.sub("", text)
    text = _html.escape(text, quote=False)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BOLD_ALT.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _ITALIC_ALT.sub(r"<i>\1</i>", text)

    for i, html in enumerate(stash):
        text = text.replace(f"\x00{i}\x00", html)
    return text


async def _responder(message, texto: str):
    """Envía con formato HTML; si el HTML quedara inválido, manda texto plano."""
    try:
        await message.reply_text(_telegram_html(texto), parse_mode=ParseMode.HTML)
    except BadRequest:
        await message.reply_text(texto)


# El agente separa sus mensajes con una línea de solo `///` (ver prompt). Lo partimos
# para enviarlo en tandas, como un humano. Tope de tandas para no spamear.
_SEP = re.compile(r"\n?\s*///\s*\n?")
_MAX_TANDAS = 3


def _en_tandas(texto: str) -> list[str]:
    partes = [p.strip() for p in _SEP.split(texto) if p.strip()]
    if len(partes) <= _MAX_TANDAS:
        return partes or [texto.strip()]
    # Si el modelo se pasó de tandas, junta el sobrante en la última.
    return partes[:_MAX_TANDAS - 1] + ["\n\n".join(partes[_MAX_TANDAS - 1:])]


async def _responder_en_tandas(update, context, texto: str):
    """Manda la respuesta como varios mensajes cortos, con 'escribiendo…' y una pausa
    proporcional entre tandas para que se sienta natural."""
    partes = _en_tandas(texto)
    for i, parte in enumerate(partes):
        if i > 0:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(min(1.6, 0.4 + len(parte) / 120))
        await _responder(update.message, parte)


def _historial_previo(user_id: str) -> list:
    """Mensajes anteriores (sin el turno actual) como objetos de LangChain."""
    return [
        HumanMessage(content=m["contenido"]) if m["tipo"] == "inbound"
        else AIMessage(content=m["contenido"])
        for m in cargar_historial(user_id, limite=20)
    ]


async def _procesar(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str,
                    username: str, extra: dict):
    """Núcleo común: arma el estado, corre el grafo, responde y persiste el historial.

    `extra` trae el tipo y los insumos del turno (texto / audio_path / imagen_path / caption).
    El texto que se guarda como inbound lo resuelve el grafo (texto_original): la
    transcripción del audio, o una etiqueta para las fotos.
    """
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        set_user_context(user_id, username, continua_sesion=continua_sesion(user_id))
        state = {"messages": _historial_previo(user_id), **extra}

        result = graph.invoke(state)
        raw = result["messages"][-1].content
        respuesta = ("".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
                     if isinstance(raw, list) else raw)

        inbound = result.get("texto_original") or extra.get("texto") or "[mensaje]"
        guardar_mensaje(user_id, "inbound", inbound, update.message.message_id)
        # En el historial guardamos la respuesta sin los separadores de tanda.
        guardar_mensaje(user_id, "outbound", _SEP.sub("\n\n", respuesta).strip())
        await _responder_en_tandas(update, context, respuesta)
    except Exception as e:
        logger.error("Error invocando grafo: %s", e, exc_info=True)
        await update.message.reply_text("❌ Error interno. Intenta de nuevo.")


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _autorizado(str(user.id)):
        await _rechazar(update); return
    nombre = user.first_name or "Ángel"
    await update.message.reply_text(
        f"Hola {nombre}. Soy Kontos, tu asistente de finanzas y despensa.\n\n"
        "Puedo ayudarte a:\n"
        "• Registrar y entender tus gastos\n"
        "• Decirte cómo vas y avisarte si te pasas del presupuesto\n"
        "• Llevar tu despensa y predecir cuándo recomprar\n"
        "• Leer capturas bancarias y tickets, o notas de voz\n\n"
        "Escríbeme, mándame un audio o una captura. ¿En qué te ayudo?"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    text = update.message.text.strip()
    logger.info("TEXT %s(%s): %s", _display_name(user), user_id, text)
    await _procesar(update, context, user_id, _display_name(user),
                    {"tipo": "texto", "texto": text})


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga la nota de voz y deja que el grafo la transcriba (rama 'transcribir')."""
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    try:
        voice = update.message.voice or update.message.audio
        tg_file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as tmp:
            audio_path = tmp.name
        await tg_file.download_to_drive(audio_path)
        try:
            await _procesar(update, context, user_id, _display_name(user),
                            {"tipo": "voz", "audio_path": audio_path})
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
    except Exception as e:
        logger.error("Error procesando voz: %s", e, exc_info=True)
        await update.message.reply_text("❌ Error procesando el audio.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga la foto y deja que el grafo la extraiga/registre (rama 'extraer_imagen')."""
    user = update.effective_user
    user_id = str(user.id)
    if not _autorizado(user_id):
        await _rechazar(update); return
    try:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        # Ruta estable por usuario: se conserva entre turnos para el caso ambiguo
        # (aclarar si era ticket o captura). La próxima foto la sobrescribe.
        img_path = os.path.join(tempfile.gettempdir(), f"kontos_img_{user_id}.jpg")
        await tg_file.download_to_drive(img_path)
        caption = update.message.caption or ""
        await _procesar(update, context, user_id, _display_name(user),
                        {"tipo": "foto", "imagen_path": img_path, "caption": caption})
    except Exception as e:
        logger.error("Error procesando foto: %s", e, exc_info=True)
        from telegram.error import TimedOut, NetworkError
        if isinstance(e, (TimedOut, NetworkError)):
            await update.message.reply_text("⏱️ Se me fue la señal al bajar la foto. Mándamela de nuevo.")
        else:
            await update.message.reply_text("❌ No pude procesar la imagen. Intenta con otra foto.")


# ── Error handler global ──────────────────────────────────────────────────────

async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    logger.error("Excepción no manejada: %s", err, exc_info=err)
    if isinstance(update, Update) and update.effective_message:
        from telegram.error import TimedOut, NetworkError
        if isinstance(err, (TimedOut, NetworkError)):
            try:
                await update.effective_message.reply_text(
                    "⏱️ Se me fue la señal un momento. Vuelve a enviármelo, por favor.")
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
        logger.info("🔒 Acceso restringido a: %s", ALLOWED_IDS)
    else:
        logger.warning("⚠️  ALLOWED_USER_IDS vacío — nadie puede acceder al bot")
    logger.info("🤖 Kontos bot escuchando...")
    app.run_polling()


if __name__ == "__main__":
    main()
