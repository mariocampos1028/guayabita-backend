"""Cliente de bajo nivel para Cloudflare R2 (API compatible con S3)."""

from __future__ import annotations

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config.r2_settings import r2_settings

logger = logging.getLogger(__name__)

AVATAR_PREFIX = "perfiles"


def avatar_object_key(user_id: int) -> str:
    """Ruta fija del avatar en el bucket: perfiles/usuario_ID.webp"""
    return f"{AVATAR_PREFIX}/usuario_{user_id}.webp"


def avatar_public_url(user_id: int) -> str:
    """URL para mostrar el avatar en el navegador."""
    key = avatar_object_key(user_id)
    if r2_settings.has_public_url:
        return f"{r2_settings.public_url}/{key}"
    return f"{r2_settings.api_public_url}/auth/avatar/{user_id}/image"


def tournament_object_key(tournament_id: int) -> str:
    return f"torneos/torneo_{tournament_id}.webp"


def tournament_public_url(tournament_id: int) -> str:
    key = tournament_object_key(tournament_id)
    if r2_settings.has_public_url:
        return f"{r2_settings.public_url}/{key}"
    return f"{r2_settings.api_public_url}/tournaments/{tournament_id}/image"


class R2StorageService:
    """Operaciones CRUD de objetos en Cloudflare R2."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=r2_settings.endpoint,
            aws_access_key_id=r2_settings.access_key_id,
            aws_secret_access_key=r2_settings.secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        self._bucket = r2_settings.bucket

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete_object(self, key: str) -> None:
        """Elimina un objeto. No falla si no existe."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError:
            logger.exception("Error al eliminar objeto R2: %s", key)
            raise

    def upload_object(self, key: str, data: bytes, content_type: str) -> None:
        """Sube un objeto al bucket."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def get_object_bytes(self, key: str) -> tuple[bytes, str]:
        """Descarga un objeto del bucket. Devuelve (bytes, content_type)."""
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"].read()
        content_type = response.get("ContentType") or "image/webp"
        return body, content_type


_r2_storage_service: R2StorageService | None = None


def get_r2_storage_service() -> R2StorageService:
    global _r2_storage_service
    if _r2_storage_service is None:
        _r2_storage_service = R2StorageService()
    return _r2_storage_service
