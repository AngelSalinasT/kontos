from graph import graph, State

# Prueba: Registrar gasto normal
state = State(
    messages=[{"role": "user", "content": "Gasté $200 en comida hoy"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Registrar gasto normal ---")
print(result["final_response"])

# Prueba: Registrar gasto fijo
state = State(
    messages=[{"role": "user", "content": "Agrega un gasto fijo de $500 para renta cada mes"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Registrar gasto fijo ---")
print(result["final_response"])

# Prueba: Registrar ingreso fijo
state = State(
    messages=[{"role": "user", "content": "Agrega un ingreso fijo de $10000 por sueldo cada mes"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Registrar ingreso fijo ---")
print(result["final_response"])

# Prueba: Consultar total
state = State(
    messages=[{"role": "user", "content": "¿Cuánto gasté este mes?"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Consultar total ---")
print(result["final_response"])

# Prueba: Listar gastos fijos
state = State(
    messages=[{"role": "user", "content": "Listar gastos fijos"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Listar gastos fijos ---")
print(result["final_response"])

# Prueba: Editar gasto normal (por ID)
state = State(
    messages=[{"role": "user", "content": "Editar gasto 1 a $250"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Editar gasto normal (ID 1) ---")
print(result["final_response"])

# Prueba: Eliminar gasto normal (por ID)
state = State(
    messages=[{"role": "user", "content": "Eliminar gasto 1"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Eliminar gasto normal (ID 1) ---")
print(result["final_response"])

# Prueba: Editar gasto fijo (por ID)
state = State(
    messages=[{"role": "user", "content": "Editar gasto fijo 1 a $600"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Editar gasto fijo (ID 1) ---")
print(result["final_response"])

# Prueba: Eliminar gasto fijo (por ID)
state = State(
    messages=[{"role": "user", "content": "Eliminar gasto fijo 1"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Eliminar gasto fijo (ID 1) ---")
print(result["final_response"])

# Prueba: Editar ingreso fijo (por ID)
state = State(
    messages=[{"role": "user", "content": "Editar ingreso fijo 1 a $12000"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Editar ingreso fijo (ID 1) ---")
print(result["final_response"])

# Prueba: Eliminar ingreso fijo (por ID)
state = State(
    messages=[{"role": "user", "content": "Eliminar ingreso fijo 1"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Eliminar ingreso fijo (ID 1) ---")
print(result["final_response"])

# Prueba: Pregunta general
state = State(
    messages=[{"role": "user", "content": "¿Qué es Kontos?"}],
    user_id="test_user_1",
    username="testuser"
)
result = graph.invoke(state)
print("--- Pregunta general ---")
print(result["final_response"]) 