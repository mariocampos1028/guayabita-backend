from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin, get_current_verified_non_admin
from app.models import (
    ReferralDashboardResponse,
    ReferralLinkResponse,
    ReferralPromoResponse,
    ReferralSettingsResponse,
    ReferralSettingsUpdateRequest,
)
from app.services import referral_service

router = APIRouter(tags=["referrals"])


@router.get("/referrals/promo", response_model=ReferralPromoResponse)
def referral_promo(
    current_user: User = Depends(get_current_verified_non_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return ReferralPromoResponse(**referral_service.get_referral_promo(db))


@router.get("/referrals/link", response_model=ReferralLinkResponse)
def get_referral_link(
    current_user: User = Depends(get_current_verified_non_admin),
    db: Session = Depends(get_db),
):
    data = referral_service.generate_referral_link(db, current_user)
    return ReferralLinkResponse(**data)


@router.get("/referrals", response_model=ReferralDashboardResponse)
def list_referrals(
    current_user: User = Depends(get_current_verified_non_admin),
    db: Session = Depends(get_db),
):
    return ReferralDashboardResponse(**referral_service.list_user_referrals(db, current_user.id))


@router.get("/admin/referrals/settings", response_model=ReferralSettingsResponse)
def admin_get_referral_settings(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return referral_service.get_settings(db)


@router.put("/admin/referrals/settings", response_model=ReferralSettingsResponse)
def admin_update_referral_settings(
    req: ReferralSettingsUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return referral_service.update_settings(
        db,
        max_referrals_per_user=req.max_referrals_per_user,
        guayabits_per_referral=req.guayabits_per_referral,
        is_enabled=req.is_enabled,
    )
