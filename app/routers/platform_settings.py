from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin, get_current_user_jwt_only
from app.models import PlatformSettingsResponse, PlatformSettingsUpdateRequest, SessionConfigResponse
from app.services import platform_settings_service, response_cache_service

router = APIRouter(tags=["platform-settings"])

PLATFORM_SETTINGS_CACHE_KEY = "cache:platform:settings:v1"
PLATFORM_SETTINGS_CACHE_TTL = 120


def _cached_settings_dict(db: Session) -> dict:
    cached = response_cache_service.get_json(PLATFORM_SETTINGS_CACHE_KEY)
    if cached is not response_cache_service.CACHE_MISS:
        return cached
    settings = platform_settings_service.get_settings(db)
    data = PlatformSettingsResponse.model_validate(settings).model_dump(mode="json")
    response_cache_service.set_json(PLATFORM_SETTINGS_CACHE_KEY, data, PLATFORM_SETTINGS_CACHE_TTL)
    return data


@router.get("/auth/session-config", response_model=SessionConfigResponse)
def session_config(
    current_user: User = Depends(get_current_user_jwt_only),
    db: Session = Depends(get_db),
):
    _ = current_user
    data = _cached_settings_dict(db)
    return SessionConfigResponse(
        lobby_inactivity_minutes=data["lobby_inactivity_minutes"],
        verification_resend_cooldown_minutes=data["verification_resend_cooldown_minutes"],
    )


@router.get("/admin/platform-settings", response_model=PlatformSettingsResponse)
def admin_get_platform_settings(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return _cached_settings_dict(db)


@router.put("/admin/platform-settings", response_model=PlatformSettingsResponse)
def admin_update_platform_settings(
    req: PlatformSettingsUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    settings = platform_settings_service.update_settings(
        db,
        lobby_inactivity_minutes=req.lobby_inactivity_minutes,
        verification_resend_cooldown_minutes=req.verification_resend_cooldown_minutes,
    )
    response_cache_service.invalidate(PLATFORM_SETTINGS_CACHE_KEY)
    return settings
