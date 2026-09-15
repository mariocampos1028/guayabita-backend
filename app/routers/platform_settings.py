from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin, get_current_user_jwt_only
from app.models import PlatformSettingsResponse, PlatformSettingsUpdateRequest, SessionConfigResponse
from app.services import platform_settings_service

router = APIRouter(tags=["platform-settings"])


@router.get("/auth/session-config", response_model=SessionConfigResponse)
def session_config(
    current_user: User = Depends(get_current_user_jwt_only),
    db: Session = Depends(get_db),
):
    _ = current_user
    settings = platform_settings_service.get_settings(db)
    return SessionConfigResponse(
        lobby_inactivity_minutes=settings.lobby_inactivity_minutes,
        verification_resend_cooldown_minutes=settings.verification_resend_cooldown_minutes,
    )


@router.get("/admin/platform-settings", response_model=PlatformSettingsResponse)
def admin_get_platform_settings(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return platform_settings_service.get_settings(db)


@router.put("/admin/platform-settings", response_model=PlatformSettingsResponse)
def admin_update_platform_settings(
    req: PlatformSettingsUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return platform_settings_service.update_settings(
        db,
        lobby_inactivity_minutes=req.lobby_inactivity_minutes,
        verification_resend_cooldown_minutes=req.verification_resend_cooldown_minutes,
    )
