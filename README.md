# Kontos

**Kontos** es un bot de Telegram minimalista que combina SQLite con herramientas de LangChain/LangGraph para registrar y consultar gastos mediante lenguaje natural. Puedes enviar mensajes como `05 Julio Soriana $385.30` y luego preguntarle *"¿Cuánto gasté esta semana?"*.

---

## 🚀 Características

- Registro de gastos con formato libre (fecha, concepto y monto).
- Consultas de totales por rango de fechas escribiendo frases como `Total de julio` o `Cuánto gasté en los últimos 5 días`.
- Base de datos local en `SQLite` sin dependencias externas.
- Arquitectura modular con nodos de LangGraph para facilitar la extensión.

---

## 📦 Tecnologías

- Python 3
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- LangGraph y LangChain
- SQLite

---

## 🔒 Privacidad

Kontos almacena toda la información **localmente** en `gastos.db`. No se envía ningún dato a servicios de terceros.

---

## 📌 Instalación y uso

1. Clona este repositorio.
2. Crea un entorno virtual y activa:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Crea un archivo `.env` con tu `TELEGRAM_BOT_TOKEN` y `GEMINI_API_KEY`:
   ```bash
   TELEGRAM_BOT_TOKEN=xxxxxxxxxx
   GEMINI_API_KEY=xxxxxxxxxx
   ```
5. Ejecuta el bot con `python bot.py` y envía mensajes desde Telegram.

Para probar el flujo sin Telegram puedes ejecutar `python test_graph.py` (requiere las dependencias instaladas).

---

## ✨ Contribuciones

¡Se agradecen pull requests! Cualquier mejora en los flujos de conversación o nuevas integraciones son bienvenidas.

---

## 📜 Licencia

MIT
