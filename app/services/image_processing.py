"""Utilidades compartidas de validación y conversión de imágenes."""

from __future__ import annotations

import io

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
OUTPUT_CONTENT_TYPE = "image/webp"


def read_upload_bytes(file: UploadFile) -> bytes:
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="Archivo inválido")
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo inválido")
    return data


def validate_upload(file: UploadFile, data: bytes) -> None:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande")


def encode_webp(image: Image.Image) -> bytes:
    for quality in (85, 80, 75, 70, 65, 60):
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=quality, method=6)
        if buffer.tell() <= 400 * 1024:
            return buffer.getvalue()
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=55, method=6)
    return buffer.getvalue()


def to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def process_square_webp(data: bytes, size: tuple[int, int]) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Archivo inválido") from exc

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize(size, Image.Resampling.LANCZOS)
    return encode_webp(to_rgb(image))


def process_prize_webp(data: bytes, max_size: tuple[int, int] = (1024, 1024)) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Archivo inválido") from exc

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return encode_webp(to_rgb(image))
