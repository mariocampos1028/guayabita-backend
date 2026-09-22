"""Cliente de bajo nivel para Cloudflare R2 (API compatible con S3)."""

from __future__ import annotations

import logging
from time import perf_counter

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config.r2_settings import r2_settings
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)

# Cache-Control a fijar como metadato del objeto en R2, para que viaje la
# cabecera correcta tanto si se sirve directo desde la URL pública de R2 como
# si se sirve por el proxy de la API cuando R2_PUBLIC_URL no está configurada.
CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"  # nombre de archivo único, nunca se reemplaza
CACHE_CONTROL_SHORT = "public, max-age=3600"  # misma ruta se reemplaza (avatar, imagen de torneo)
CACHE_CONTROL_PRIVATE = "private, no-store"  # comprobantes de pago: nunca en caché

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


def store_public_url(key: str) -> str:
    if r2_settings.has_public_url:
        return f"{r2_settings.public_url}/{key}"
    return f"{r2_settings.api_public_url}/store/media/{key}"


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
        started = perf_counter()
        outcome = "ok"
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return False
            outcome = "error"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._record("head", outcome, started)

    def delete_object(self, key: str) -> None:
        """Elimina un objeto. No falla si no existe."""
        started = perf_counter()
        outcome = "ok"
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError:
            outcome = "error"
            logger.exception("Error al eliminar objeto R2: %s", key)
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._record("delete", outcome, started)

    def upload_object(
        self, key: str, data: bytes, content_type: str, *, cache_control: str | None = None,
    ) -> None:
        """Sube un objeto al bucket.

        ``cache_control`` se guarda como metadato del objeto: R2 lo devuelve
        como cabecera ``Cache-Control`` cuando el archivo se sirve desde la
        URL pública, sin que la API tenga que intervenir.
        """
        started = perf_counter()
        outcome = "ok"
        try:
            extra: dict = {}
            if cache_control:
                extra["CacheControl"] = cache_control
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                **extra,
            )
        except Exception:
            outcome = "error"
            raise
        finally:
            self._record("put", outcome, started, len(data))

    def get_object_bytes(self, key: str) -> tuple[bytes, str]:
        """Descarga un objeto del bucket. Devuelve (bytes, content_type)."""
        started = perf_counter()
        outcome = "ok"
        data_size = 0
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            data_size = len(body)
            content_type = response.get("ContentType") or "image/webp"
            return body, content_type
        except Exception:
            outcome = "error"
            raise
        finally:
            self._record("get", outcome, started, data_size)

    @staticmethod
    def _record(operation: str, outcome: str, started: float, byte_count: int = 0) -> None:
        labels = {"operation": operation, "outcome": outcome}
        metrics.increment("guayabita_r2_operations", labels)
        metrics.observe("guayabita_r2_operation_seconds", perf_counter() - started, labels)
        if byte_count:
            metrics.increment("guayabita_r2_bytes", {"operation": operation}, byte_count)


_r2_storage_service: R2StorageService | None = None


def get_r2_storage_service() -> R2StorageService:
    global _r2_storage_service
    if _r2_storage_service is None:
        _r2_storage_service = R2StorageService()
    return _r2_storage_service
