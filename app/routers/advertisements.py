"""Router de publicidad: endpoints de administración y consulta para usuarios."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin, get_current_user
from app.models import (
    AdvertisementBannerResponse,
    AdvertisementCreateRequest,
    AdvertisementForUserResponse,
    AdvertisementResponse,
    OccupiedSectionsResponse,
    ADVERTISEMENT_SECTIONS,
)
from app.services import advertisement_service

# ── Router admin ───────────────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/admin/advertisements", tags=["admin-advertisements"])


@admin_router.get("/banners", response_model=list[AdvertisementBannerResponse])
async def list_banners(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lista todos los banners disponibles con indicador de uso activo."""
    _ = admin
    return advertisement_service.list_banners(db)


@admin_router.post("/banners", response_model=AdvertisementBannerResponse, status_code=201)
async def upload_banner(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Sube un nuevo banner .webp a Cloudflare R2 y lo registra en la base de datos."""
    _ = admin
    data = await file.read()
    return advertisement_service.upload_banner(db, file, data)


@admin_router.delete("/banners/{banner_id}", status_code=204)
async def delete_banner(
    banner_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Elimina un banner si no está en uso por una publicidad activa."""
    _ = admin
    advertisement_service.delete_banner(db, banner_id)


@admin_router.get("/occupied-sections", response_model=OccupiedSectionsResponse)
def get_occupied_sections(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Devuelve las secciones que ya tienen una publicidad activa asignada."""
    _ = admin
    occupied = advertisement_service.get_occupied_sections(db)
    return OccupiedSectionsResponse(occupied=occupied)


@admin_router.get("", response_model=list[AdvertisementResponse])
def list_advertisements(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lista el historial de publicidades con sus secciones y banner."""
    _ = admin
    return advertisement_service.list_advertisements(db)


@admin_router.post("", response_model=AdvertisementResponse, status_code=201)
def create_advertisement(
    payload: AdvertisementCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Crea una nueva publicidad activa, validando conflictos de sección."""
    return advertisement_service.create_advertisement(db, payload, admin.id)


@admin_router.patch("/{advertisement_id}/activate", response_model=AdvertisementResponse)
def activate_advertisement(
    advertisement_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Activa una publicidad inactiva, verificando que sus secciones estén libres."""
    _ = admin
    return advertisement_service.activate_advertisement(db, advertisement_id)


@admin_router.patch("/{advertisement_id}/deactivate", response_model=AdvertisementResponse)
def deactivate_advertisement(
    advertisement_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Desactiva una publicidad activa."""
    _ = admin
    return advertisement_service.deactivate_advertisement(db, advertisement_id)


# ── Router usuario ──────────────────────────────────────────────────────────────

user_router = APIRouter(prefix="/advertisements", tags=["advertisements"])


@user_router.get("/available", response_model=Optional[AdvertisementForUserResponse])
def get_available_advertisement(
    section: str = Query(..., description=f"Sección consultada. Valores: {', '.join(ADVERTISEMENT_SECTIONS)}"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Devuelve la publicidad activa correspondiente al usuario para la sección dada,
    si el saldo del usuario es menor que el umbral configurado.
    Devuelve null si no hay publicidad aplicable.
    """
    return advertisement_service.get_available_advertisement(db, current_user, section)
