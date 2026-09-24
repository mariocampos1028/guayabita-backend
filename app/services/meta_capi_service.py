"""API de Conversiones de Meta — envía server-side los mismos eventos de
conversión que ya manda el navegador con el Pixel (ver tracking.service.ts en
el frontend), para recuperar los que el navegador pierde por bloqueadores de
anuncios o por las restricciones de iOS.

Cada evento usa el MISMO `event_id` que ya usó el pixel del navegador para el
mismo hecho de negocio (la referencia del pedido para `Purchase`, `reg-{id}`
para `CompleteRegistration`) — Meta deduplica automáticamente el que llega
por las dos vías, así que nunca se cuenta doble.

Deliberadamente no lanza ninguna excepción: un fallo de red hacia Meta, un
token vencido o un rechazo de la API jamás debe tumbar un registro ni una
compra. Si no hay Pixel ID o token configurados, es un no-op silencioso —
mismo criterio que el pixel del navegador cuando no hay `metaPixelId`.
"""

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"

META_PIXEL_ID = os.getenv("META_PIXEL_ID", "").strip()
META_CAPI_ACCESS_TOKEN = os.getenv("META_CAPI_ACCESS_TOKEN", "").strip()
# Opcional: mientras se valida en Meta → "Probar eventos". Quitar en producción
# real, porque los eventos con este código no cuentan para la pauta.
META_CAPI_TEST_EVENT_CODE = os.getenv("META_CAPI_TEST_EVENT_CODE", "").strip()

ENABLED = bool(META_PIXEL_ID and META_CAPI_ACCESS_TOKEN)


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:4200").rstrip("/")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_email(email: str | None) -> str | None:
    if not email:
        return None
    return _sha256(email.strip().lower())


def _hash_phone(phone: str | None) -> str | None:
    """Meta exige E.164 sin '+' antes del hash. Los teléfonos que se
    registran en Guayabita son colombianos sin indicativo (10 dígitos)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"57{digits}"
    return _sha256(digits)


def send_event(
    *,
    event_name: str,
    event_id: str,
    event_source_url: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    external_id: int | str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    fbp: str | None = None,
    fbc: str | None = None,
    custom_data: dict | None = None,
) -> None:
    if not ENABLED:
        return

    user_data: dict = {}
    hashed_email = _hash_email(email)
    if hashed_email:
        user_data["em"] = [hashed_email]
    hashed_phone = _hash_phone(phone)
    if hashed_phone:
        user_data["ph"] = [hashed_phone]
    if external_id is not None:
        user_data["external_id"] = [_sha256(str(external_id))]
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent
    if fbp:
        user_data["fbp"] = fbp
    if fbc:
        user_data["fbc"] = fbc

    event: dict = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "website",
        "event_source_url": event_source_url or f"{_frontend_url()}/",
        "user_data": user_data,
    }
    if custom_data:
        event["custom_data"] = custom_data

    payload: dict = {"data": [event]}
    if META_CAPI_TEST_EVENT_CODE:
        payload["test_event_code"] = META_CAPI_TEST_EVENT_CODE

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{META_PIXEL_ID}/events"
        f"?access_token={META_CAPI_ACCESS_TOKEN}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Meta CAPI rechazó el evento %s: %s — %s", event_name, exc.code, body)
    except Exception as exc:  # noqa: BLE001 — nunca debe romper el flujo de negocio
        logger.warning("Meta CAPI: error enviando evento %s: %s", event_name, exc)
