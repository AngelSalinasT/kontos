# tools.py
from db import insertar_movimiento, total_quincenal

def insertar_movimiento_tool(user_id, username, fecha, concepto, monto, categoria_id, origen):
    from db import insertar_movimiento
    insertar_movimiento(user_id, username, fecha, concepto, float(monto), categoria_id, origen)
    return True # Indica éxito

def consultar_total_quincenal_tool(user_id, fecha_inicio, fecha_fin):
    total = total_quincenal(user_id, fecha_inicio, fecha_fin)
    return float(total) if total is not None else 0.0 # Asegura float y 0.0 si es None
