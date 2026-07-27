import os

_TRUE = frozenset({"1", "true", "yes", "on"})


def is_maintenance_mode() -> bool:
    return os.getenv("MAINTENANCE_MODE", "false").strip().lower() in _TRUE


def maintenance_message() -> str:
    return os.getenv(
        "MAINTENANCE_MESSAGE",
        "Estamos preparando algo especial. ¡Vuelve pronto!",
    ).strip()
