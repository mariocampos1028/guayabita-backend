from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models_db import PlatformSettings

DEFAULT_LOBBY_INACTIVITY_MINUTES = 3
DEFAULT_VERIFICATION_RESEND_COOLDOWN_MINUTES = 5

# Cache de valores simples (no instancias ORM) para evitar objetos detached entre requests.
_values_cache: tuple[int, int] | None = None


def invalidate_platform_settings_cache() -> None:
    global _values_cache
    _values_cache = None


def _ensure_settings_row(db: Session) -> PlatformSettings:
    settings = db.query(PlatformSettings).filter(PlatformSettings.id == 1).first()
    if settings is not None:
        return settings

    now = datetime.now(timezone.utc)
    settings = PlatformSettings(
        id=1,
        lobby_inactivity_minutes=DEFAULT_LOBBY_INACTIVITY_MINUTES,
        verification_resend_cooldown_minutes=DEFAULT_VERIFICATION_RESEND_COOLDOWN_MINUTES,
        updated_at=now,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    invalidate_platform_settings_cache()
    return settings


def get_settings(db: Session) -> PlatformSettings:
    return _ensure_settings_row(db)


def get_lobby_session_ttl_seconds(db: Session) -> int:
    global _values_cache
    if _values_cache is not None:
        return max(1, _values_cache[0]) * 60

    settings = _ensure_settings_row(db)
    _values_cache = (
        settings.lobby_inactivity_minutes,
        settings.verification_resend_cooldown_minutes,
    )
    return max(1, settings.lobby_inactivity_minutes) * 60


def get_verification_resend_cooldown_seconds(db: Session) -> int:
    global _values_cache
    if _values_cache is not None:
        return max(1, _values_cache[1]) * 60

    settings = _ensure_settings_row(db)
    _values_cache = (
        settings.lobby_inactivity_minutes,
        settings.verification_resend_cooldown_minutes,
    )
    return max(1, settings.verification_resend_cooldown_minutes) * 60


def update_settings(
    db: Session,
    *,
    lobby_inactivity_minutes: int,
    verification_resend_cooldown_minutes: int,
) -> PlatformSettings:
    if lobby_inactivity_minutes < 1 or lobby_inactivity_minutes > 120:
        raise HTTPException(
            status_code=400,
            detail="La inactividad de sesión debe estar entre 1 y 120 minutos",
        )
    if verification_resend_cooldown_minutes < 1 or verification_resend_cooldown_minutes > 60:
        raise HTTPException(
            status_code=400,
            detail="La espera para reenviar verificación debe estar entre 1 y 60 minutos",
        )

    settings = _ensure_settings_row(db)
    settings.lobby_inactivity_minutes = lobby_inactivity_minutes
    settings.verification_resend_cooldown_minutes = verification_resend_cooldown_minutes
    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    invalidate_platform_settings_cache()
    _values_cache = (settings.lobby_inactivity_minutes, settings.verification_resend_cooldown_minutes)
    return settings
