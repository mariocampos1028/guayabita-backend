"""API de Eventos de TikTok — equivalente a `meta_capi_service.py` pero para
TikTok Ads: envía server-side los mismos eventos de conversión que ya manda
el navegador con el Pixel (ver tracking.service.ts y tiktok-pixel.adapter.ts
en el frontend), para recuperar los que el navegador pierde por bloqueadores
de anuncios o por las restricciones de iOS.

Cada evento usa el MISMO `event_id` que ya usó el pixel del navegador para el
mismo hecho de negocio (la referencia del pedido para `CompletePayment`,
`reg-{id}` para `CompleteRegistration`) — TikTok deduplica automáticamente el
que llega por las dos vías, así que nunca se cuenta doble.

Deliberadamente no lanza ninguna excepción: un fallo de red hacia TikTok, un
token vencido o un rechazo de la API jamás debe tumbar un registro ni una
compra. Si no hay Pixel ID o token configurados, es un no-op silencioso —
mismo criterio que el pixel del navegador cuando no hay `tiktokPixelId`.
"""

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

EVENTS_API_VERSION = "v1.3"

TIKTOK_PIXEL_ID = os.getenv("TIKTOK_PIXEL_ID", "").strip()
TIKTOK_CAPI_ACCESS_TOKEN = os.getenv("TIKTOK_CAPI_ACCESS_TOKEN", "").strip()
# Opcional: mientras se valida en TikTok → "Test Events". Quitar en producción
# real, porque los eventos con este código no cuentan para la pauta.
TIKTOK_CAPI_TEST_EVENT_CODE = os.getenv("TIKTOK_CAPI_TEST_EVENT_CODE", "").strip()

ENABLED = bool(TIKTOK_PIXEL_ID and TIKTOK_CAPI_ACCESS_TOKEN)


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:4200").rstrip("/")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_email(email: str | None) -> str | None:
    if not email:
        return None
    return _sha256(email.strip().lower())


def _hash_phone_e164(phone: str | None) -> str | None:
    """TikTok exige E.164 CON '+' antes del hash — a diferencia de Meta, que
    lo exige sin '+'. Los teléfonos que se registran en Guayabita son
    colombianos sin indicativo (10 dígitos)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"57{digits}"
    return _sha256(f"+{digits}")


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
    ttp: str | None = None,
    ttclid: str | None = None,
    custom_data: dict | None = None,
) -> None:
    if not ENABLED:
        return

    user: dict = {}
    hashed_email = _hash_email(email)
    if hashed_email:
        user["email"] = hashed_email
    hashed_phone = _hash_phone_e164(phone)
    if hashed_phone:
        user["phone"] = hashed_phone
    if external_id is not None:
        user["external_id"] = _sha256(str(external_id))
    if client_ip:
        user["ip"] = client_ip
    if user_agent:
        user["user_agent"] = user_agent
    if ttp:
        user["ttp"] = ttp
    if ttclid:
        user["ttclid"] = ttclid

    event: dict = {
        "event": event_name,
        "event_time": int(time.time()),
        "event_id": event_id,
        "user": user,
        "page": {"url": event_source_url or f"{_frontend_url()}/"},
    }
    if custom_data is not None:
        event["properties"] = custom_data

    payload: dict = {
        "event_source": "web",
        "event_source_id": TIKTOK_PIXEL_ID,
        "data": [event],
    }
    if TIKTOK_CAPI_TEST_EVENT_CODE:
        payload["test_event_code"] = TIKTOK_CAPI_TEST_EVENT_CODE

    url = f"https://business-api.tiktok.com/open_api/{EVENTS_API_VERSION}/event/track/"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Access-Token": TIKTOK_CAPI_ACCESS_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("TikTok Events API rechazó el evento %s: %s — %s", event_name, exc.code, body)
    except Exception as exc:  # noqa: BLE001 — nunca debe romper el flujo de negocio
        logger.warning("TikTok Events API: error enviando evento %s: %s", event_name, exc)
