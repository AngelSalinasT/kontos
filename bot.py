# bot.py
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from graph import graph

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    telegram_user_id = str(update.effective_user.id) # ID del usuario
    telegram_username = update.effective_user.username # Nombre de usuario (puede ser None)
    telegram_first_name = update.effective_user.first_name # Primer nombre
    
    # Usar el username si existe, si no, el primer nombre, si no, el ID
    display_username = telegram_username if telegram_username else telegram_first_name
    if not display_username:
        display_username = f"Usuario_{telegram_user_id}" # Fallback si no hay nombre ni username
    
    print(f"📩 Mensaje recibido de {display_username} ({telegram_user_id}): {user_message}")
    
    try:
        result = graph.invoke({
            "messages": [HumanMessage(content=user_message)],
            "user_id": telegram_user_id,
            "username": display_username, # <-- ¡PASANDO EL NOMBRE DE USUARIO!
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

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot escuchando...")
    app.run_polling()

if __name__ == "__main__":
    main()
