"""Configuración de Cloudflare R2 leída desde variables de entorno."""

import os
from dataclasses import dataclass

_PLACEHOLDER_VALUES = {"", "REEMPLAZAR", "reemplazar"}


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _is_configured(value: str | None) -> bool:
    return _clean(value).lower() not in _PLACEHOLDER_VALUES


@dataclass(frozen=True)
class R2Settings:
    access_key_id: str
    secret_access_key: str
    bucket: str
    endpoint: str
    public_url: str | None
    api_public_url: str

    @property
    def has_public_url(self) -> bool:
        return self.public_url is not None

    @property
    def is_configured(self) -> bool:
        return all(
            _is_configured(value)
            for value in (
                self.access_key_id,
                self.secret_access_key,
                self.bucket,
                self.endpoint,
            )
        )


def get_r2_settings() -> R2Settings:
    public_url_raw = _clean(os.getenv("R2_PUBLIC_URL"))
    public_url = public_url_raw.rstrip("/") if _is_configured(public_url_raw) else None

    api_public_url = _clean(os.getenv("API_PUBLIC_URL")) or "http://localhost:8000"

    return R2Settings(
        access_key_id=os.getenv("R2_ACCESS_KEY_ID", "REEMPLAZAR"),
        secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "REEMPLAZAR"),
        bucket=os.getenv("R2_BUCKET", "guayabita"),
        endpoint=os.getenv("R2_ENDPOINT", "REEMPLAZAR"),
        public_url=public_url,
        api_public_url=api_public_url.rstrip("/"),
    )


r2_settings = get_r2_settings()
