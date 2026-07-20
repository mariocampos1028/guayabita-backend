"""Validación, procesamiento y almacenamiento de fotos de perfil."""

from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile

from app.services.image_processing import (
    OUTPUT_CONTENT_TYPE,
    process_square_webp,
    read_upload_bytes,
    validate_upload,
)
from app.services.r2_storage_service import (
    avatar_object_key,
    avatar_public_url,
    get_r2_storage_service,
)

logger = logging.getLogger(__name__)
AVATAR_SIZE = (512, 512)


def upload_user_avatar(user_id: int, file: UploadFile) -> str:
    """Procesa y sube el avatar. Reemplaza el archivo anterior si existe."""
    raw = read_upload_bytes(file)
    validate_upload(file, raw)
    webp_bytes = process_square_webp(raw, AVATAR_SIZE)

    storage = get_r2_storage_service()
    key = avatar_object_key(user_id)

    try:
        if storage.object_exists(key):
            storage.delete_object(key)
        storage.upload_object(key, webp_bytes, OUTPUT_CONTENT_TYPE)
    except Exception as exc:
        logger.exception("Error al subir avatar a R2 para usuario %s", user_id)
        raise HTTPException(status_code=500, detail="Error al subir la imagen") from exc

    return avatar_public_url(user_id)


def delete_user_avatar(user_id: int) -> None:
    """Elimina el avatar del usuario en R2."""
    storage = get_r2_storage_service()
    key = avatar_object_key(user_id)

    try:
        if storage.object_exists(key):
            storage.delete_object(key)
    except Exception as exc:
        logger.exception("Error al eliminar avatar de R2 para usuario %s", user_id)
        raise HTTPException(status_code=500, detail="Error al eliminar la imagen") from exc


def get_user_avatar_bytes(user_id: int) -> tuple[bytes, str]:
    """Obtiene los bytes del avatar desde R2 (para el proxy API)."""
    storage = get_r2_storage_service()
    key = avatar_object_key(user_id)

    try:
        if not storage.object_exists(key):
            raise HTTPException(status_code=404, detail="Avatar no encontrado")
        return storage.get_object_bytes(key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error al leer avatar de R2 para usuario %s", user_id)
        raise HTTPException(status_code=500, detail="Error al obtener la imagen") from exc
