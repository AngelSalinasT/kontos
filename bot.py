# bot.py - Se mantiene igual
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from graph import graph # Asegúrate de que 'graph' se importa correctamente
from telegram.ext import CommandHandler


load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "ℹ️ *Cómo usar Kontos:*\n\n"
        "- Registra movimientos enviando:\n"
        '"02 Julio Starbucks $120"\n'
        "- Consulta totales diciendo:\n"
        '"Total del mes"\n\n'
        "Más funciones pronto 🚀"
    )
    await update.message.reply_text(mensaje)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "👋 Hola, soy Kontos.\n\n"
        "📌 Registra tus gastos enviando mensajes como:\n"
        '"05 Julio Soriana $385.30"\n\n'
        "📌 Pregunta por totales:\n"
        '"Total del mes"\n\n'
        "Mantén tus finanzas claras, sin complicaciones. 💸"
    )
    await update.message.reply_text(mensaje)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    telegram_user_id = str(update.effective_user.id) # Obtener el ID del usuario
    print(f"📩 Mensaje recibido de {telegram_user_id}: {user_message}")
    
    try:
        result = graph.invoke({
            "messages": [HumanMessage(content=user_message)],
            "user_id": telegram_user_id, # Pasar el ID del usuario al grafo
        })
        
        final_response = result.get("final_response")
        
        if not final_response:
            final_response = "❌ No pude procesar tu solicitud. Por favor, intenta de nuevo con otro formato."
        
        print(f"✅ Respuesta final: {final_response}")
        
        await update.message.reply_text(final_response)
        
    except Exception as e:
        print(f"❌ Error en handle_message: {e}")
        await update.message.reply_text("❌ Error interno del bot. Por favor, intenta de nuevo más tarde.")

def main():
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN no está configurado en el archivo .env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build() # Crear la aplicación del bot
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("start", start_command)) # Manejo del comando /start
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)) # Manejo de mensajes de texto
    print("🤖 Bot escuchando...") 
    app.run_polling()

if __name__ == "__main__":
    main()
