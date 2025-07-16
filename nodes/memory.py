# Nodo de memoria para manejar el estado conversacional en RAM por usuario

user_memory = {}

def set_user_state(user_id, state):
    """Guarda o actualiza el estado de un usuario."""
    user_memory[user_id] = state


def get_user_state(user_id):
    """Obtiene el estado actual de un usuario. Devuelve None si no existe."""
    return user_memory.get(user_id)


def clear_user_state(user_id):
    """Elimina el estado guardado de un usuario."""
    if user_id in user_memory:
        del user_memory[user_id] 