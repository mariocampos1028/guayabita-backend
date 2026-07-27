from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.maintenance import is_maintenance_mode, maintenance_message

# Rutas que siguen disponibles durante mantenimiento
_EXEMPT_EXACT = frozenset({"/", "/status", "/docs", "/openapi.json", "/redoc"})
_EXEMPT_PREFIXES = (
    "/payments/wompi/webhook",
    "/payments/wompi/return",
)


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_maintenance_mode():
            return await call_next(request)

        if request.method == "OPTIONS" or _is_exempt(request.url.path):
            return await call_next(request)

        return JSONResponse(
            status_code=503,
            content={
                "detail": maintenance_message(),
                "code": "MAINTENANCE_MODE",
            },
        )
