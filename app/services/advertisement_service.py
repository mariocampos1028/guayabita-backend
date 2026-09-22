"""Servicio de publicidad: CRUD de banners, publicidades y motor de selección."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models_db import (
    AdvertisementBanner,
    Advertisement,
    AdvertisementSection,
    User,
)
from app.models import (
    AdvertisementBannerResponse,
    AdvertisementCreateRequest,
    AdvertisementForUserResponse,
    AdvertisementResponse,
    ADVERTISEMENT_SECTIONS,
)
from app.services.r2_storage_service import get_r2_storage_service, R2StorageService
from app.config.r2_settings import r2_settings

logger = logging.getLogger(__name__)

# ── Constantes ─────────────────────────────────────────────────────────────────

BANNER_PREFIX = "promotions"
MAX_BANNER_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_MIME_TYPES = {"image/webp"}
ALLOWED_EXTENSIONS = {".webp"}

# Listas administrativas de tamaño acotado por diseño (banners/publicidades se crean
# manualmente por admins, no por usuarios): un límite fijo alto evita una consulta sin
# tope sin necesitar paginación completa para un catálogo que nunca crece con el tráfico.
ADMIN_LIST_SAFETY_LIMIT = 300


# ── Helpers privados ────────────────────────────────────────────────────────────

def _banner_object_key() -> str:
    return f"{BANNER_PREFIX}/banner_{uuid.uuid4().hex}.webp"


def _banner_public_url(object_key: str) -> str:
    if r2_settings.has_public_url:
        return f"{r2_settings.public_url}/{object_key}"
    return f"{r2_settings.api_public_url}/admin/advertisements/banners/{object_key}/image"


def _is_banner_in_active_use(db: Session, banner_id: int) -> bool:
    stmt = (
        select(Advertisement)
        .where(Advertisement.banner_id == banner_id, Advertisement.is_active.is_(True))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _get_active_sections(db: Session, exclude_advertisement_id: Optional[int] = None) -> set[str]:
    """Devuelve el conjunto de secciones ocupadas por publicidades activas."""
    stmt = (
        select(AdvertisementSection.section)
        .join(Advertisement, AdvertisementSection.advertisement_id == Advertisement.id)
        .where(Advertisement.is_active.is_(True))
    )
    if exclude_advertisement_id is not None:
        stmt = stmt.where(Advertisement.id != exclude_advertisement_id)
    rows = db.execute(stmt).scalars().all()
    return set(rows)


def _load_advertisement(db: Session, advertisement_id: int) -> Advertisement:
    stmt = (
        select(Advertisement)
        .options(
            selectinload(Advertisement.banner),
            selectinload(Advertisement.sections),
        )
        .where(Advertisement.id == advertisement_id)
    )
    adv = db.execute(stmt).scalar_one_or_none()
    if adv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicidad no encontrada")
    return adv


def _advertisement_to_response(adv: Advertisement) -> AdvertisementResponse:
    return AdvertisementResponse(
        id=adv.id,
        banner_id=adv.banner_id,
        banner=AdvertisementBannerResponse.model_validate(adv.banner),
        balance_threshold=adv.balance_threshold,
        frequency=adv.frequency,
        is_active=adv.is_active,
        sections=[s.section for s in adv.sections],
        created_at=adv.created_at,
        updated_at=adv.updated_at,
    )


# ── Banners ────────────────────────────────────────────────────────────────────

def validate_banner_file(file: UploadFile, data: bytes) -> None:
    """Valida extensión, MIME type y tamaño del banner."""
    filename = (file.filename or "").lower()
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Solo se aceptan imágenes .webp. Extensión recibida: '{ext}'",
        )
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Solo se aceptan imágenes image/webp. MIME recibido: '{content_type}'",
        )
    if len(data) > MAX_BANNER_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El archivo supera el tamaño máximo permitido de 2 MB.",
        )
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo está vacío.",
        )


def list_banners(db: Session) -> list[AdvertisementBannerResponse]:
    """Lista todos los banners con indicador de uso activo."""
    banners = db.execute(
        select(AdvertisementBanner)
        .order_by(AdvertisementBanner.created_at.desc())
        .limit(ADMIN_LIST_SAFETY_LIMIT)
    ).scalars().all()

    # Obtener IDs de banners usados por publicidades activas
    active_banner_ids_stmt = (
        select(Advertisement.banner_id)
        .where(Advertisement.is_active.is_(True))
        .distinct()
    )
    active_ids: set[int] = set(db.execute(active_banner_ids_stmt).scalars().all())

    result = []
    for b in banners:
        resp = AdvertisementBannerResponse.model_validate(b)
        resp = resp.model_copy(update={"in_use": b.id in active_ids})
        result.append(resp)
    return result


def upload_banner(db: Session, file: UploadFile, data: bytes) -> AdvertisementBannerResponse:
    """Valida, sube a R2 y registra un nuevo banner en la base de datos."""
    validate_banner_file(file, data)

    r2: R2StorageService = get_r2_storage_service()
    object_key = _banner_object_key()
    public_url = _banner_public_url(object_key)

    # Subir a R2 primero; si falla, no guardamos nada en BD
    try:
        r2.upload_object(object_key, data, "image/webp")
    except Exception as exc:
        logger.exception("Error al subir banner a R2: %s", object_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al subir la imagen al almacenamiento. Intenta de nuevo.",
        ) from exc

    # Guardar en BD; si falla, limpiar R2
    try:
        banner = AdvertisementBanner(
            original_name=file.filename or "banner.webp",
            object_key=object_key,
            public_url=public_url,
            mime_type="image/webp",
            file_size=len(data),
        )
        db.add(banner)
        db.commit()
        db.refresh(banner)
    except Exception as exc:
        logger.exception("Error al guardar banner en BD, revirtiendo R2: %s", object_key)
        try:
            r2.delete_object(object_key)
        except Exception:
            logger.exception("Fallo al limpiar objeto huérfano R2: %s", object_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar el banner. La imagen fue eliminada del almacenamiento.",
        ) from exc

    return AdvertisementBannerResponse.model_validate(banner)


def delete_banner(db: Session, banner_id: int) -> None:
    """Elimina un banner si no está en uso por ninguna publicidad activa."""
    banner = db.get(AdvertisementBanner, banner_id)
    if banner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Banner no encontrado")

    if _is_banner_in_active_use(db, banner_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este banner está siendo utilizado por una publicidad activa y no puede eliminarse.",
        )

    object_key = banner.object_key

    # Eliminar de BD primero
    db.delete(banner)
    db.commit()

    # Luego de R2 (si falla, el registro ya no existe, pero el objeto queda huérfano en R2 — lo logueamos)
    try:
        get_r2_storage_service().delete_object(object_key)
    except Exception:
        logger.exception(
            "Banner eliminado de BD pero falló la eliminación en R2. Objeto huérfano: %s", object_key
        )


# ── Publicidades ───────────────────────────────────────────────────────────────

def list_advertisements(db: Session) -> list[AdvertisementResponse]:
    """Lista todas las publicidades con sus secciones y banner."""
    stmt = (
        select(Advertisement)
        .options(
            selectinload(Advertisement.banner),
            selectinload(Advertisement.sections),
        )
        .order_by(Advertisement.created_at.desc())
        .limit(ADMIN_LIST_SAFETY_LIMIT)
    )
    advs = db.execute(stmt).scalars().all()
    return [_advertisement_to_response(a) for a in advs]


def create_advertisement(
    db: Session,
    payload: AdvertisementCreateRequest,
    admin_id: int,
) -> AdvertisementResponse:
    """Crea una publicidad validando conflictos de sección."""
    # Verificar que el banner existe
    banner = db.get(AdvertisementBanner, payload.banner_id)
    if banner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Banner no encontrado")

    # Validar que las secciones sean valores permitidos
    for sec in payload.sections:
        if sec not in ADVERTISEMENT_SECTIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sección inválida: '{sec}'",
            )

    # Verificar conflictos de sección con publicidades activas
    occupied = _get_active_sections(db)
    conflicts = [s for s in payload.sections if s in occupied]
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Las siguientes secciones ya tienen una publicidad activa: {', '.join(conflicts)}",
        )

    adv = Advertisement(
        banner_id=payload.banner_id,
        balance_threshold=payload.balance_threshold,
        frequency=payload.frequency,
        is_active=True,
        created_by_id=admin_id,
    )
    db.add(adv)
    db.flush()  # obtener ID antes de agregar secciones

    for sec in payload.sections:
        db.add(AdvertisementSection(advertisement_id=adv.id, section=sec))

    db.commit()
    db.refresh(adv)

    return _advertisement_to_response(_load_advertisement(db, adv.id))


def activate_advertisement(db: Session, advertisement_id: int) -> AdvertisementResponse:
    """Activa una publicidad verificando que sus secciones no estén ocupadas."""
    adv = _load_advertisement(db, advertisement_id)

    if adv.is_active:
        return _advertisement_to_response(adv)

    adv_sections = {s.section for s in adv.sections}
    occupied = _get_active_sections(db, exclude_advertisement_id=advertisement_id)
    conflicts = adv_sections & occupied
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede activar: las siguientes secciones ya tienen otra publicidad activa: {', '.join(sorted(conflicts))}",
        )

    adv.is_active = True
    db.commit()
    db.refresh(adv)
    return _advertisement_to_response(_load_advertisement(db, adv.id))


def deactivate_advertisement(db: Session, advertisement_id: int) -> AdvertisementResponse:
    """Desactiva una publicidad."""
    adv = _load_advertisement(db, advertisement_id)
    adv.is_active = False
    db.commit()
    db.refresh(adv)
    return _advertisement_to_response(_load_advertisement(db, adv.id))


def get_occupied_sections(db: Session) -> list[str]:
    """Devuelve las secciones actualmente ocupadas por publicidades activas."""
    return sorted(_get_active_sections(db))


# ── Motor de publicidad ─────────────────────────────────────────────────────────

def get_available_advertisement(
    db: Session,
    user: User,
    section: str,
) -> Optional[AdvertisementForUserResponse]:
    """
    Determina si existe una publicidad que corresponde mostrar al usuario.

    Reglas:
      - La publicidad debe estar activa.
      - Debe tener la sección solicitada configurada.
      - El saldo del usuario debe ser estrictamente menor que balance_threshold.
    """
    if section not in ADVERTISEMENT_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Sección inválida: '{section}'. Valores permitidos: {', '.join(ADVERTISEMENT_SECTIONS)}",
        )

    stmt = (
        select(Advertisement)
        .join(AdvertisementSection, AdvertisementSection.advertisement_id == Advertisement.id)
        .options(selectinload(Advertisement.banner))
        .where(
            Advertisement.is_active.is_(True),
            AdvertisementSection.section == section,
        )
        .limit(1)
    )
    adv = db.execute(stmt).scalar_one_or_none()

    if adv is None:
        return None

    # Condición de saldo: saldo estrictamente < threshold
    if user.balance >= adv.balance_threshold:
        return None

    return AdvertisementForUserResponse(
        id=adv.id,
        banner_public_url=adv.banner.public_url,
        frequency=adv.frequency,
        balance_threshold=adv.balance_threshold,
        section=section,
    )
