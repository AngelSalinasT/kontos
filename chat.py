"""
Interfaz CLI para probar Kontos sin Telegram.
Simula el flujo del bot: texto, fotos y audio (las tres ramas del grafo).

Uso:
  python3 chat.py                    # sesión interactiva
  python3 chat.py "ver despensa"     # un solo mensaje y salir

Comandos especiales dentro de la sesión:
  /foto <ruta>      Simula enviar una foto (captura o ticket)
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
from persistence.historial import guardar_mensaje, cargar_historial, continua_sesion
from context import set_user_context
from db import init_db

USER_ID   = os.getenv("SEED_USER_ID", "cli_user")
USERNAME  = "Angel"

RESET, BOLD, CYAN, GREEN, YELLOW, RED, DIM = (
    "\033[0m", "\033[1m", "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[2m")


def _historial_previo():
    return [
        HumanMessage(content=m["contenido"]) if m["tipo"] == "inbound"
        else AIMessage(content=m["contenido"])
        for m in cargar_historial(USER_ID, limite=20)
    ]


def _invocar(extra: dict) -> str:
    """Corre el grafo con los insumos del turno (igual que bot._procesar, sin Telegram)."""
    set_user_context(USER_ID, USERNAME, continua_sesion=continua_sesion(USER_ID))
    state = {"messages": _historial_previo(), **extra}
    result = graph.invoke(state)
    raw = result["messages"][-1].content
    respuesta = ("".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
                 if isinstance(raw, list) else raw)
    inbound = result.get("texto_original") or extra.get("texto") or "[mensaje]"
    guardar_mensaje(USER_ID, "inbound", inbound)
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
    print(f"{YELLOW}  🖼️  Procesando imagen: {ruta}{RESET}")
    return _invocar({"tipo": "foto", "imagen_path": ruta, "caption": ""})


def _handle_voz(args: str) -> str:
    ruta = args.strip()
    if not ruta:
        return f"{RED}Uso: /voz <ruta_al_archivo>{RESET}"
    if not os.path.exists(ruta):
        return f"{RED}No encontré el archivo: {ruta}{RESET}"
    print(f"{YELLOW}  🎙️  Transcribiendo: {ruta}{RESET}")
    return _invocar({"tipo": "voz", "audio_path": ruta})


def _handle_seed():
    print(f"{YELLOW}  🌱 Cargando productos de Costco...{RESET}")
    from seed import seed
    seed(USER_ID, USERNAME)
    return "✅ Productos cargados. Escribe 'ver despensa' para verlos."


def run_once(mensaje: str):
    init_db()
    low = mensaje.lower()
    if low.startswith("/foto"):
        print(_handle_foto(mensaje[5:]))
    elif low.startswith("/voz"):
        print(_handle_voz(mensaje[4:]))
    elif low == "/seed":
        print(_handle_seed())
    else:
        print(_invocar({"tipo": "texto", "texto": mensaje}))


def run_interactive():
    init_db()
    print(f"\n{CYAN}{BOLD}{'─'*55}")
    print("  Kontos CLI  —  simulador de Telegram")
    print(f"{'─'*55}{RESET}")
    print(f"{DIM}  USER_ID: {USER_ID}  |  /salir para salir{RESET}\n")
    _print_bot(
        f"Hola {USERNAME}. Soy Kontos. Comandos: /foto <ruta>, /voz <ruta>, "
        "/seed, /reset, /salir")

    while True:
        try:
            entrada = input(f"{GREEN}{BOLD}Tú: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}  Adiós.{RESET}\n"); break
        if not entrada:
            continue
        low = entrada.lower()
        if low in ("/salir", "/exit", "/quit", "salir", "exit"):
            print(f"\n{DIM}  Adiós.{RESET}\n"); break
        elif low == "/reset":
            print(f"{YELLOW}  Historial de sesión: la BD se mantiene.{RESET}"); continue
        elif low == "/seed":
            _print_user("/seed"); _print_bot(_handle_seed()); continue
        elif low.startswith("/foto"):
            _print_user(entrada); _print_bot(_handle_foto(entrada[5:])); continue
        elif low.startswith("/voz"):
            _print_user(entrada); _print_bot(_handle_voz(entrada[4:])); continue
        elif low.startswith("/"):
            print(f"{RED}  Comando desconocido. Usa /foto, /voz, /seed, /reset, /salir{RESET}"); continue
        _print_user(entrada)
        try:
            _print_bot(_invocar({"tipo": "texto", "texto": entrada}))
        except Exception as e:
            _print_bot(f"❌ Error interno: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_once(" ".join(sys.argv[1:]))
    else:
        run_interactive()
