"""Caché Redis explícita para respuestas públicas, sin datos personales."""

from __future__ import annotations

import json
from typing import Any

CACHE_MISS = object()


def _redis():
    # Evita una importación circular al iniciar los servicios de autenticación.
    from app.services.room_service import redis
    return redis


def get_json(key: str) -> Any:
    try:
        raw = _redis().get(key)
    except Exception:
        return CACHE_MISS
    if not raw:
        return CACHE_MISS
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        try:
            _redis().delete(key)
        except Exception:
            pass
        return CACHE_MISS


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        _redis().set(key, json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
    except Exception:
        # La caché acelera lecturas, pero nunca debe bloquear una respuesta válida.
        return


def invalidate(*keys: str) -> None:
    if keys:
        try:
            _redis().delete(*keys)
        except Exception:
            return
