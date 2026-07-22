import hashlib
import os
import secrets
from typing import Any


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


WOMPI_ENV = _env("WOMPI_ENV", "sandbox")
WOMPI_PUBLIC_KEY = _env("WOMPI_PUBLIC_KEY")
WOMPI_PRIVATE_KEY = _env("WOMPI_PRIVATE_KEY")
WOMPI_INTEGRITY_SECRET = _env("WOMPI_INTEGRITY_SECRET") or _env("WOMPI_INTEGRITY_KEY")
WOMPI_EVENTS_SECRET = _env("WOMPI_EVENTS_SECRET") or _env("WOMPI_EVENTS_KEY")
WOMPI_REDIRECT_URL = _env("WOMPI_REDIRECT_URL")


def resolve_redirect_url() -> str | None:
    """Wompi puede rechazar redirect http://localhost en el widget (403)."""
    configured = WOMPI_REDIRECT_URL or f"{_env('FRONTEND_URL', 'http://localhost:4200')}/recargar/resultado"
    lowered = configured.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered:
        return None
    return configured

WOMPI_API_BASE = (
    "https://production.wompi.co/v1"
    if WOMPI_ENV == "production"
    else "https://sandbox.wompi.co/v1"
)


def ensure_wompi_configured() -> None:
    missing = []
    if not WOMPI_PUBLIC_KEY:
        missing.append("WOMPI_PUBLIC_KEY")
    if not WOMPI_INTEGRITY_SECRET:
        missing.append("WOMPI_INTEGRITY_SECRET")
    if not WOMPI_EVENTS_SECRET:
        missing.append("WOMPI_EVENTS_SECRET")
    if missing:
        raise RuntimeError(f"Faltan variables de entorno Wompi: {', '.join(missing)}")


def generate_reference(purchase_id: int) -> str:
    token = secrets.token_hex(4).upper()
    return f"GUA-{purchase_id}-{token}"


def generate_placeholder_reference() -> str:
    """Referencia temporal única hasta tener el id de la compra."""
    return f"GUA-TMP-{secrets.token_hex(8).upper()}"


def price_to_cents(price: float) -> int:
    return int(round(price * 100))


def build_integrity_signature(reference: str, amount_in_cents: int, currency: str = "COP") -> str:
    payload = f"{reference}{amount_in_cents}{currency}{WOMPI_INTEGRITY_SECRET}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_event_checksum(event: dict[str, Any]) -> bool:
    signature = event.get("signature") or {}
    properties: list[str] = signature.get("properties") or []
    checksum = (signature.get("checksum") or "").upper()
    timestamp = event.get("timestamp")
    data = event.get("data") or {}

    if not properties or not checksum or timestamp is None:
        return False

    parts: list[str] = []
    for prop in properties:
        value = _resolve_property(data, prop)
        if value is None:
            return False
        parts.append(str(value))
    parts.append(str(timestamp))
    parts.append(WOMPI_EVENTS_SECRET)
    calculated = hashlib.sha256("".join(parts).encode("utf-8")).hexdigest().upper()
    return calculated == checksum


def _resolve_property(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
