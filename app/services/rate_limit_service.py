"""Límite de tasa genérico, respaldado por un contador atómico en Redis.

``INCR`` es atómico en Redis (una sola operación server-side): a diferencia del
``GET -> validar en Python -> SET`` que tenía el join de salas o el webhook de
Wompi antes de corregirlos, aquí no hace falta Lua — muchas peticiones
concurrentes incrementando la misma clave nunca pierden un conteo entre sí.

El TTL se fija solo en el primer incremento de la ventana (``count == 1``),
que por la atomicidad de INCR le ocurre a una sola petición aunque varias
lleguen al mismo tiempo.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

RATE_LIMIT_PREFIX = "rate:"


def _redis():
    # Import perezoso: evita el ciclo de import con room_service al cargar el módulo.
    from app.services.room_service import redis
    return redis


def check_rate_limit(
    bucket: str,
    identifier: str,
    *,
    max_requests: int,
    window_seconds: int,
    message: str = "Demasiadas solicitudes. Intenta de nuevo en unos minutos.",
) -> None:
    """Lanza 429 si ``identifier`` superó ``max_requests`` en ``window_seconds``.

    Si Redis no responde, deja pasar la solicitud: un límite de tasa nunca debe
    tumbar el servicio completo por un problema de infraestructura ajeno.
    """
    key = f"{RATE_LIMIT_PREFIX}{bucket}:{identifier}"
    try:
        redis = _redis()
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, window_seconds)
    except Exception:
        return

    if count > max_requests:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)


def client_ip(request: Request) -> str:
    """IP real del cliente detrás del proxy de Railway.

    Toma la primera IP de ``X-Forwarded-For`` (la del cliente original, no la
    del proxy); si el header no está presente, usa la conexión directa.

    Nota: no se pudo verificar contra una petición real en producción desde
    este entorno — confirma en logs que el valor extraído es una IP externa
    real y no la del proxy interno de Railway antes de confiar en él para
    banear IPs, por ejemplo.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
