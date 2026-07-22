import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine
from app.db import models_db  # noqa: F401 — necesario para que Base conozca los modelos
from app.db.database import Base
from app.db.migrations import run_startup_migrations
from app.routers.auth import router as auth_router
from app.routers.rooms import router as rooms_router
from app.routers.game import router as game_router
from app.routers.tournaments import router as tournaments_router
from app.routers.audit import router as audit_router
from app.routers.packages import router as packages_router
from app.routers.payments import router as payments_router

load_dotenv()

logger = logging.getLogger(__name__)

# Crea las tablas en PostgreSQL si no existen
Base.metadata.create_all(bind=engine)
run_startup_migrations()

app = FastAPI(title="Guayabita API", version="2.0.0")

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


@app.get("/")
def root():
    return {"message": "Guayabita API v2 running"}
