"""Herramientas que el agente puede usar. ALL_TOOLS es la lista que recibe el ReAct.

Nota: el procesamiento de imágenes NO es una tool — es determinista y ocurre antes
del agente (nodes/extraer_imagen). De imagen, el agente solo conserva el caso de
aclaración (`clasificar_imagen_pendiente`) y la gestión de tickets.
"""
from tools.gastos import (
    registrar_gasto,
    listar_gastos,
    editar_gasto,
    eliminar_gasto,
    consultar_total,
)
from tools.fijos import (
    registrar_gasto_fijo,
    listar_gastos_fijos,
    editar_gasto_fijo,
    eliminar_gasto_fijo,
    registrar_ingreso_fijo,
    listar_ingresos_fijos,
    editar_ingreso_fijo,
    eliminar_ingreso_fijo,
)
from tools.despensa import (
    agregar_producto_despensa,
    listar_productos_despensa,
    editar_producto_despensa,
    quitar_producto_despensa,
    registrar_compra_despensa,
    listar_compras_despensa,
    editar_compra_despensa,
    eliminar_compra_despensa,
    generar_lista_despensa,
    consultar_prediccion_despensa,
)
from tools.presupuestos import (
    crear_presupuesto,
    ver_presupuestos,
    editar_presupuesto,
    eliminar_presupuesto,
)
from tools.analisis import (
    resumen_financiero,
    calcular,
)
from tools.imagen import (
    clasificar_imagen_pendiente,
    listar_tickets,
    eliminar_ticket,
)

ALL_TOOLS = [
    # Análisis y cálculo (base para conversar con números exactos)
    resumen_financiero,
    calcular,
    # Gastos
    registrar_gasto,
    listar_gastos,
    editar_gasto,
    eliminar_gasto,
    consultar_total,
    # Fijos
    registrar_gasto_fijo,
    listar_gastos_fijos,
    editar_gasto_fijo,
    eliminar_gasto_fijo,
    registrar_ingreso_fijo,
    listar_ingresos_fijos,
    editar_ingreso_fijo,
    eliminar_ingreso_fijo,
    # Despensa
    agregar_producto_despensa,
    listar_productos_despensa,
    editar_producto_despensa,
    quitar_producto_despensa,
    registrar_compra_despensa,
    listar_compras_despensa,
    editar_compra_despensa,
    eliminar_compra_despensa,
    generar_lista_despensa,
    consultar_prediccion_despensa,
    # Presupuestos
    crear_presupuesto,
    ver_presupuestos,
    editar_presupuesto,
    eliminar_presupuesto,
    # Imagen (solo aclaración + tickets)
    clasificar_imagen_pendiente,
    listar_tickets,
    eliminar_ticket,
]
