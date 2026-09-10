"""Procesamiento y almacenamiento R2 de medios de tienda y comprobantes."""

from __future__ import annotations

import logging
import secrets

from fastapi import HTTPException, UploadFile

from app.services.image_processing import process_prize_webp
from app.services.r2_storage_service import get_r2_storage_service, store_public_url

logger = logging.getLogger(__name__)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/webm"}
RECEIPT_TYPES = IMAGE_TYPES | {"application/pdf"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_RECEIPT_BYTES = 10 * 1024 * 1024


def _read(file: UploadFile, allowed: set[str], max_bytes: int) -> tuple[bytes, str]:
    content_type = (file.content_type or "").lower()
    if not file.filename or content_type not in allowed:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail="El archivo supera el tamaño permitido")
    return data, content_type


def upload_product_media(product_id: int, file: UploadFile) -> tuple[str, str, str]:
    content_type = (file.content_type or "").lower()
    if content_type in IMAGE_TYPES:
        raw, _ = _read(file, IMAGE_TYPES, MAX_IMAGE_BYTES)
        data = process_prize_webp(raw, (1400, 1400))
        media_type, extension, output_type = "image", "webp", "image/webp"
    elif content_type in VIDEO_TYPES:
        data, output_type = _read(file, VIDEO_TYPES, MAX_VIDEO_BYTES)
        media_type = "video"
        extension = "webm" if output_type == "video/webm" else "mp4"
    else:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes, MP4 o WebM")

    key = f"tienda/productos/{product_id}/{secrets.token_hex(12)}.{extension}"
    try:
        get_r2_storage_service().upload_object(key, data, output_type)
    except Exception as exc:
        logger.exception("No fue posible subir medio del producto %s", product_id)
        raise HTTPException(status_code=500, detail="No fue posible almacenar el archivo") from exc
    return media_type, key, store_public_url(key)


def upload_payment_receipt(order_reference: str, file: UploadFile) -> str:
    raw, content_type = _read(file, RECEIPT_TYPES, MAX_RECEIPT_BYTES)
    if content_type in IMAGE_TYPES:
        data = process_prize_webp(raw, (1600, 1600))
        extension, output_type = "webp", "image/webp"
    else:
        data, extension, output_type = raw, "pdf", "application/pdf"
    key = f"tienda/comprobantes/{order_reference}.{extension}"
    try:
        get_r2_storage_service().upload_object(key, data, output_type)
    except Exception as exc:
        logger.exception("No fue posible subir comprobante %s", order_reference)
        raise HTTPException(status_code=500, detail="No fue posible almacenar el comprobante") from exc
    return key


def payment_receipt_url(order_id: int) -> str:
    return f"/admin/store/orders/{order_id}/receipt"


def delete_store_object(key: str) -> None:
    try:
        get_r2_storage_service().delete_object(key)
    except Exception as exc:
        logger.exception("No fue posible eliminar objeto de tienda %s", key)
        raise HTTPException(status_code=500, detail="No fue posible eliminar el archivo") from exc


def get_store_object(key: str) -> tuple[bytes, str]:
    try:
        return get_r2_storage_service().get_object_bytes(key)
    except Exception as exc:
        logger.exception("No fue posible leer objeto de tienda %s", key)
        raise HTTPException(status_code=404, detail="Archivo no encontrado") from exc
