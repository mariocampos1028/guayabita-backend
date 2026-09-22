"""Trazabilidad de peticiones y métricas HTTP con baja cardinalidad."""

from __future__ import annotations

import json
import logging
import uuid
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.metrics import metrics

logger = logging.getLogger("guayabita.request")


def _route_name(request: Request) -> str:
    route = request.scope.get("route")
    if route and getattr(route, "path", None):
        return route.path
    # Evita que una URL con IDs o códigos cree una serie de métricas por usuario.
    return request.url.path if request.url.path in {"/", "/status"} else "/unmatched"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = perf_counter() - started
            labels = {
                "method": request.method,
                "route": _route_name(request),
                "status": str(status_code),
            }
            metrics.increment("guayabita_http_requests", labels)
            metrics.observe("guayabita_http_request_seconds", duration, labels)
            logger.info(json.dumps({
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "route": labels["route"],
                "status": status_code,
                "duration_ms": round(duration * 1000, 2),
            }, ensure_ascii=False))
