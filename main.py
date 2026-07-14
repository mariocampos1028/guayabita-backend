import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.db.database import engine
from app.db import models_db  # noqa: F401 — necesario para que Base conozca los modelos
from app.db.database import Base
from app.routers.auth import router as auth_router
from app.routers.rooms import router as rooms_router
from app.routers.game import router as game_router

load_dotenv()

# Crea las tablas en PostgreSQL si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Guayabita API", version="2.0.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(game_router)


@app.get("/")
def root():
    return {"message": "Guayabita API v2 running"}
