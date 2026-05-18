"""
Interfaz CLI para probar Kontos sin Telegram.
Simula exactamente el flujo del bot: texto, fotos y audio.

Uso:
  python3 chat.py                    # sesión interactiva
  python3 chat.py "ver despensa"     # un solo mensaje y salir

Comandos especiales dentro de la sesión:
  /foto <ruta>      Simula enviar una foto de ticket
  /voz <ruta>       Simula enviar una nota de voz
  /seed             Carga los productos de Costco (seed.py)
  /reset            Limpia el historial de esta sesión
  /salir            Sale del chat
"""
import os, sys, textwrap

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from graph import graph
from langchain_core.messages import HumanMessage, AIMessage
from nodes.historial import guardar_mensaje, cargar_historial
from db import init_db

USER_ID   = os.getenv("SEED_USER_ID", "cli_user")
USERNAME  = "Claude"

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"


def _cargar_historial_como_mensajes():
    hist = cargar_historial(USER_ID, limite=20)
    msgs = []
    for m in hist:
        if m["tipo"] == "inbound":
            msgs.append(HumanMessage(content=m["contenido"]))
        else:
            msgs.append(AIMessage(content=m["contenido"]))
    return msgs


def _build_state(texto: str, decision=None, imagen_path=None, es_voz=False):
    previos = _cargar_historial_como_mensajes()
    return {
        "messages":    previos + [HumanMessage(content=texto)],
        "user_id":     USER_ID,
        "username":    USERNAME,
        "decision":    decision,
        "parsed_data": None,
        "final_response": None,
        "imagen_path": imagen_path,
        "es_voz":      es_voz,
    }


def _invocar(texto: str, decision=None, imagen_path=None, es_voz=False) -> str:
    state = _build_state(texto, decision=decision, imagen_path=imagen_path, es_voz=es_voz)
    result = graph.invoke(state)
    respuesta = result.get("final_response") or "❌ Sin respuesta."
    guardar_mensaje(USER_ID, "inbound",  texto)
    guardar_mensaje(USER_ID, "outbound", respuesta)
    return respuesta


def _print_bot(texto: str):
    print(f"\n{CYAN}{BOLD}Kontos:{RESET}")
    for linea in texto.split("\n"):
        print(f"  {linea}")
    print()


def _print_user(texto: str):
    wrapped = textwrap.fill(texto, width=60, subsequent_indent="         ")
    print(f"\n{GREEN}{BOLD}Tú:{RESET}      {wrapped}")


def _handle_foto(args: str) -> str:
    ruta = args.strip()
    if not ruta:
        return f"{RED}Uso: /foto <ruta_al_archivo>{RESET}"
    if not os.path.exists(ruta):
        return f"{RED}No encontré el archivo: {ruta}{RESET}"
    print(f"{YELLOW}  🧾 Procesando ticket: {ruta}{RESET}")
    return _invocar("[foto de ticket]", decision="procesar_ticket", imagen_path=ruta)


def _handle_voz(args: str) -> str:
    ruta = args.strip()
    if not ruta:
        return f"{RED}Uso: /voz <ruta_al_archivo>{RESET}"
    if not os.path.exists(ruta):
        return f"{RED}No encontré el archivo: {ruta}{RESET}"
    print(f"{YELLOW}  🎙️  Transcribiendo: {ruta}{RESET}")
    try:
        from services.whisper_service import transcribir
        texto = transcribir(ruta)
        if not texto:
            return "❌ No pude transcribir el audio."
        print(f"{DIM}  → Transcripción: \"{texto}\"{RESET}")
        return _invocar(texto, es_voz=True)
    except ImportError:
        return "⚠️  faster-whisper no instalado. Instala con: pip install faster-whisper pydub"


def _handle_seed():
    print(f"{YELLOW}  🌱 Cargando productos de Costco...{RESET}")
    from seed import seed
    seed(USER_ID, USERNAME)
    return "✅ Productos cargados. Escribe 'ver despensa' para verlos."


def run_once(mensaje: str):
    """Modo no interactivo: un mensaje y salir."""
    init_db()
    respuesta = _invocar(mensaje)
    print(respuesta)


def run_interactive():
    """Modo interactivo — simula Telegram."""
    init_db()

    print(f"\n{CYAN}{BOLD}{'─'*55}")
    print("  Kontos CLI  —  simulador de Telegram")
    print(f"{'─'*55}{RESET}")
    print(f"{DIM}  USER_ID: {USER_ID}  |  /salir para salir{RESET}\n")

    # Saludo inicial igual al bot real
    _print_bot(
        f"👋 Hola {USERNAME}! Soy Kontos, tu asistente de finanzas y despensa.\n\n"
        "Escribe cualquier mensaje. Comandos especiales:\n"
        "  /foto <ruta>  — simula foto de ticket\n"
        "  /voz  <ruta>  — simula nota de voz\n"
        "  /seed         — carga productos de Costco\n"
        "  /reset        — borra historial de sesión\n"
        "  /salir        — salir"
    )

    while True:
        try:
            entrada = input(f"{GREEN}{BOLD}Tú: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}  Adiós.{RESET}\n")
            break

        if not entrada:
            continue

        low = entrada.lower()

        if low in ("/salir", "/exit", "/quit", "salir", "exit"):
            print(f"\n{DIM}  Adiós.{RESET}\n")
            break

        elif low == "/reset":
            print(f"{YELLOW}  Historial de sesión borrado (la BD se mantiene).{RESET}")
            continue

        elif low == "/seed":
            _print_user("/seed")
            _print_bot(_handle_seed())
            continue

        elif low.startswith("/foto"):
            _print_user(entrada)
            _print_bot(_handle_foto(entrada[5:]))
            continue

        elif low.startswith("/voz"):
            _print_user(entrada)
            _print_bot(_handle_voz(entrada[4:]))
            continue

        elif low.startswith("/"):
            print(f"{RED}  Comando desconocido. Usa /foto, /voz, /seed, /reset, /salir{RESET}")
            continue

        _print_user(entrada)
        try:
            respuesta = _invocar(entrada)
            _print_bot(respuesta)
        except Exception as e:
            _print_bot(f"❌ Error interno: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_once(" ".join(sys.argv[1:]))
    else:
        run_interactive()
