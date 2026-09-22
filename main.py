import logging
import os
import secrets
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine
from app.db import models_db  # noqa: F401 — registra los modelos en Base.metadata
from app.middleware.maintenance import MaintenanceMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.observability.metrics import metrics
from app.config.maintenance import is_maintenance_mode, maintenance_message
from app.routers.auth import router as auth_router
from app.routers.rooms import router as rooms_router
from app.routers.game import router as game_router
from app.routers.tournaments import router as tournaments_router
from app.routers.audit import router as audit_router
from app.routers.packages import router as packages_router
from app.routers.payments import router as payments_router
from app.routers.store import router as store_router
from app.routers.support import router as support_router
from app.routers.admin_users import router as admin_users_router
from app.routers.referrals import router as referrals_router
from app.routers.platform_settings import router as platform_settings_router
from app.routers.balance_movements import router as balance_movements_router
from app.routers.advertisements import admin_router as advertisements_admin_router
from app.routers.advertisements import user_router as advertisements_user_router

load_dotenv()

logger = logging.getLogger(__name__)

# El esquema lo aplica el Pre-deploy Command de Railway ejecutando
# run_startup_migrations() una sola vez por despliegue. Hacerlo aquí lo repetiría
# en cada worker al arrancar, y varios procesos creando el mismo índice a la vez
# se pisan entre sí.

app = FastAPI(title="Guayabita API", version="2.0.0")

app.add_middleware(MaintenanceMiddleware)
app.add_middleware(ObservabilityMiddleware)

origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno de base de datos"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})

app.include_router(auth_router)
app.include_router(tournaments_router)
app.include_router(rooms_router)
app.include_router(game_router)
app.include_router(audit_router)
app.include_router(packages_router)
app.include_router(payments_router)
app.include_router(store_router)
app.include_router(support_router)
app.include_router(admin_users_router)
app.include_router(referrals_router)
app.include_router(platform_settings_router)
app.include_router(balance_movements_router)
app.include_router(advertisements_admin_router)
app.include_router(advertisements_user_router)


@app.get("/")
def root():
    return {"message": "Guayabita API v2 running"}


@app.get("/status")
def status():
    return {
        "maintenance_mode": is_maintenance_mode(),
        "message": maintenance_message(),
    }


@app.get("/internal/metrics", include_in_schema=False)
def internal_metrics(request: Request):
    """Métricas de proceso. Se habilita únicamente con token configurado."""
    token = os.getenv("OBSERVABILITY_METRICS_TOKEN", "")
    supplied = request.headers.get("X-Metrics-Token", "")
    if not token or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=404, detail="No encontrado")

    pool = engine.pool
    if hasattr(pool, "checkedout"):
        metrics.set_gauge("guayabita_sql_pool_checked_out", pool.checkedout())
    if hasattr(pool, "size"):
        metrics.set_gauge("guayabita_sql_pool_size", pool.size())
    return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")
