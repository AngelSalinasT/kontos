"""
Prueba CRUD completo a través del agente Kontos:
  - Gastos: crear, listar, editar, eliminar
  - Gastos fijos: crear, listar, editar, eliminar
  - Presupuestos: crear, ver, editar, eliminar
  - Despensa productos: crear, listar, editar, desactivar
  - Despensa compras: registrar, listar, editar, eliminar
  - Ticket simulado: procesar imagen de prueba, listar, eliminar

Uso: python3 test_crud.py
"""
import os, sys, re, textwrap

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from graph import graph
from langchain_core.messages import HumanMessage, AIMessage
from persistence.historial import guardar_mensaje, cargar_historial
from db import init_db, get_conn

USER_ID = "crud_tester"

# ─── helpers ──────────────────────────────────────────────────────────────────

def _run(texto, decision=None, imagen_path=None):
    hist = cargar_historial(USER_ID, limite=6)
    previos = []
    for m in hist:
        cls = HumanMessage if m["tipo"] == "inbound" else AIMessage
        previos.append(cls(content=m["contenido"]))
    state = {
        "messages":       previos + [HumanMessage(content=texto)],
        "user_id":        USER_ID,
        "username":       "Tester",
        "decision":       decision,
        "parsed_data":    None,
        "final_response": None,
        "imagen_path":    imagen_path,
        "es_voz":         False,
    }
    result = graph.invoke(state)
    resp = result.get("final_response") or "❌ Sin respuesta"
    guardar_mensaje(USER_ID, "inbound",  texto)
    guardar_mensaje(USER_ID, "outbound", resp)
    return resp


OK = 0
FAIL = 0

def test(label, texto, decision=None, imagen_path=None, expect=None):
    global OK, FAIL
    SEP = "─" * 58
    print(f"\n{SEP}")
    print(f"  👤 {label}")
    print(f"     → \"{texto}\"")
    print(SEP)
    try:
        resp = _run(texto, decision=decision, imagen_path=imagen_path)
        for linea in resp.split("\n"):
            print(f"  🤖 {linea}")
        if expect and not any(e.lower() in resp.lower() for e in expect):
            print(f"\n  ⚠️  Respuesta inesperada (esperaba alguno de: {expect})")
            FAIL += 1
        else:
            OK += 1
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        FAIL += 1


def header(titulo):
    print(f"\n{'═'*58}")
    print(f"  {titulo}")
    print(f"{'═'*58}")


def first_id_in(resp) -> str:
    """Extrae el primer número de ID de una respuesta."""
    m = re.search(r"ID[:\s#]*(\d+)", resp, re.IGNORECASE)
    return m.group(1) if m else "1"


# ─── setup ────────────────────────────────────────────────────────────────────

init_db()

# Limpia datos del usuario de prueba para empezar fresco
with get_conn() as conn:
    conn.execute("DELETE FROM movimientos        WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM gastos_fijos       WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM ingresos_fijos     WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM presupuestos       WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM productos          WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM compras_despensa   WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM historial_mensajes WHERE user_id=?", (USER_ID,))
    conn.execute("DELETE FROM tickets_ocr        WHERE user_id=?", (USER_ID,))

print("\n✅ Base de datos limpia para el test")


# ══════════════════════════════════════════════════════════════
# BLOQUE 1: CRUD Gastos
# ══════════════════════════════════════════════════════════════
header("BLOQUE 1 — CRUD Gastos individuales")

test("Crear gasto 1",   "Gasté $320 en farmacia el 10 de mayo",  expect=["registr", "320"])
test("Crear gasto 2",   "Pagué $1200 en Walmart hoy",             expect=["registr", "1200"])
test("Crear gasto 3",   "Gasté $85 en café Starbucks hoy",        expect=["registr", "85"])

r = _run("listar gastos")
print(f"\n{'─'*58}\n  👤 Listar gastos\n{'─'*58}")
for l in r.split("\n"): print(f"  🤖 {l}")
OK += 1

gasto_id = first_id_in(r)
print(f"\n  [→ ID extraído para editar/eliminar: {gasto_id}]")

test("Editar gasto",   f"editar gasto {gasto_id} a $400",           expect=["actualiz", "400", "✅"])
test("Listar tras edit", "ver gastos",                               expect=["400", "gasto"])
test("Eliminar gasto", f"eliminar gasto {gasto_id}",                 expect=["eliminad", "borrad", "✅"])
test("Listar tras delete", "listar gastos",                          expect=["gasto", "ID", "no hay"])


# ══════════════════════════════════════════════════════════════
# BLOQUE 2: CRUD Gastos Fijos
# ══════════════════════════════════════════════════════════════
header("BLOQUE 2 — CRUD Gastos Fijos")

test("Crear gasto fijo",    "gasto fijo renta $5000 mensual",           expect=["registr", "5000"])
test("Crear gasto fijo 2",  "gasto fijo Netflix $259 mensual",          expect=["registr", "259"])
test("Listar gastos fijos", "listar gastos fijos",                       expect=["renta", "netflix"])

r2 = _run("listar gastos fijos")
gf_id = first_id_in(r2)
print(f"  [→ ID gasto fijo: {gf_id}]")

test("Editar gasto fijo",   f"editar gasto fijo {gf_id} a $5500",       expect=["actualiz", "5500", "✅"])
test("Eliminar gasto fijo", f"eliminar gasto fijo {gf_id}",              expect=["eliminad", "borrad", "✅"])
test("Listar tras delete",  "listar gastos fijos",                        expect=["netflix", "gasto"])


# ══════════════════════════════════════════════════════════════
# BLOQUE 3: CRUD Presupuestos
# ══════════════════════════════════════════════════════════════
header("BLOQUE 3 — CRUD Presupuestos")

test("Crear presupuesto comida",      "crear presupuesto comida $3000",     expect=["creado", "3000"])
test("Crear presupuesto transporte",  "crear presupuesto transporte $1500", expect=["creado", "1500"])
test("Gasté para ver avance",         "Gasté $800 en super Chedraui hoy",   expect=["registr", "800"])
test("Ver presupuestos",              "cómo voy",                            expect=["presupuesto", "%", "░"])

r3 = _run("cómo voy")
pres_id = first_id_in(r3)
print(f"  [→ ID presupuesto: {pres_id}]")

test("Editar presupuesto",  f"editar presupuesto {pres_id} a $3500",        expect=["actualiz", "3500", "✅"])
test("Eliminar presupuesto",f"eliminar presupuesto {pres_id}",               expect=["eliminad", "borrad", "✅"])
test("Ver tras delete",     "cómo voy",                                       expect=["presupuesto"])


# ══════════════════════════════════════════════════════════════
# BLOQUE 4: CRUD Despensa — Productos
# ══════════════════════════════════════════════════════════════
header("BLOQUE 4 — CRUD Despensa: Productos")

test("Agregar Leche",        "agregar producto Leche Kirkland categoría despensa precio 428",   expect=["leche", "✅"])
test("Agregar Atún",         "agregar producto Atún Dolores categoría despensa precio 193",      expect=["atún", "tun", "✅"])
test("Agregar Papel higiénico", "agregar producto Papel Higiénico Kirkland categoría higiene precio 413", expect=["papel", "✅"])
test("Listar despensa",      "ver despensa",                                                     expect=["leche", "atún", "papel", "ID"])

r4 = _run("ver despensa")
prod_id = first_id_in(r4)
print(f"  [→ ID producto: {prod_id}]")

test("Editar producto",      f"editar producto {prod_id} precio 450",          expect=["actualiz", "✅"])
test("Desactivar producto",  f"quitar producto {prod_id}",                      expect=["desactiv", "eliminad", "✅"])
test("Listar tras desactivar","ver despensa",                                    expect=["ID", "producto"])


# ══════════════════════════════════════════════════════════════
# BLOQUE 5: CRUD Despensa — Compras
# ══════════════════════════════════════════════════════════════
header("BLOQUE 5 — CRUD Despensa: Compras")

# Primero re-activar / asegurar que hay productos
with get_conn() as conn:
    conn.execute("UPDATE productos SET activo=1 WHERE user_id=?", (USER_ID,))

test("Registrar compra Atún",   "compré Atún Dolores $193 en Costco",          expect=["compra", "✅", "atún", "tun"])
test("Registrar compra Leche",  "compré Leche Kirkland $428 en Costco",         expect=["compra", "✅", "leche"])
test("Listar compras",          "historial compras",                             expect=["compra", "ID", "leche", "atún"])

r5 = _run("historial compras")
compra_id = first_id_in(r5)
print(f"  [→ ID compra: {compra_id}]")

test("Editar compra",           f"editar compra {compra_id} a $200",            expect=["actualiz", "✅"])
test("Eliminar compra",         f"eliminar compra {compra_id}",                  expect=["eliminad", "borrad", "✅"])
test("Listar tras delete",      "historial compras",                              expect=["compra", "ID"])

test("Lista despensa inteligente", "lista de despensa",                          expect=["leche", "atún", "tun", "despensa"])
test("Predicción",              "cuándo compro la leche",                        expect=["leche", "compra", "día", "patron", "predic", "suficiente"])


# ══════════════════════════════════════════════════════════════
# BLOQUE 6: Ticket simulado (imagen de prueba)
# ══════════════════════════════════════════════════════════════
header("BLOQUE 6 — Ticket simulado (OCR)")

# Crear imagen de ticket de prueba con texto plano
ticket_path = "/tmp/ticket_prueba.png"
try:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (400, 300), color="white")
    draw = ImageDraw.Draw(img)
    ticket_text = [
        "COSTCO WHOLESALE",
        "Querétaro  08/Sep/2025",
        "─────────────────────",
        "LECHE KIRKLAND 12L    $428.13",
        "ATUN DOLORES 10PZ     $193.35",
        "PAPEL HIG KIRKLAND    $413.61",
        "─────────────────────",
        "TOTAL                $1035.09",
        "GRACIAS POR SU COMPRA",
    ]
    y = 20
    for linea in ticket_text:
        draw.text((20, y), linea, fill="black")
        y += 28
    img.save(ticket_path)
    print(f"\n  ✅ Imagen de ticket creada: {ticket_path}")
    ticket_ok = True
except Exception as e:
    print(f"\n  ⚠️  No se pudo crear imagen ({e}) — saltando OCR")
    ticket_ok = False

if ticket_ok:
    test("Procesar ticket OCR",  "[foto de ticket]",
         decision="procesar_ticket", imagen_path=ticket_path,
         expect=["ticket", "registr", "producto", "leche", "atún", "tun", "papel", "compra", "OCR", "procesado"])
    test("Listar tickets",       "ver tickets",     expect=["ticket", "ID"])
    test("Listar compras post-OCR", "historial compras", expect=["compra", "ID"])

    r6 = _run("ver tickets")
    tick_id = first_id_in(r6)
    test("Eliminar ticket",      f"eliminar ticket {tick_id}", expect=["eliminad", "borrad", "✅"])


# ══════════════════════════════════════════════════════════════
# RESUMEN
# ══════════════════════════════════════════════════════════════
print(f"\n{'═'*58}")
print(f"  RESULTADO FINAL: {OK} OK  |  {FAIL} con advertencia")
print(f"{'═'*58}\n")
