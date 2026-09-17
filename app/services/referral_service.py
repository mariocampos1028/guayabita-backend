import os
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models_db import Referral, ReferralSettings, User
from app.services.auth_service import update_user_balance
from app.services.email_validation import mask_email

DEFAULT_MAX_REFERRALS = 10
DEFAULT_GUAYABITS_PER_REFERRAL = 1000.0


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:4200").rstrip("/")


def get_settings(db: Session) -> ReferralSettings:
    settings = db.query(ReferralSettings).filter(ReferralSettings.id == 1).first()
    if settings is None:
        now = datetime.now(timezone.utc)
        settings = ReferralSettings(
            id=1,
            max_referrals_per_user=DEFAULT_MAX_REFERRALS,
            guayabits_per_referral=DEFAULT_GUAYABITS_PER_REFERRAL,
            is_enabled=True,
            updated_at=now,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def count_rewarded_referrals(db: Session, referrer_id: int) -> int:
    return (
        db.query(Referral)
        .filter(
            Referral.referrer_id == referrer_id,
            Referral.guayabits_rewarded > 0,
        )
        .count()
    )


def count_active_referrals(db: Session, referrer_id: int) -> int:
    return (
        db.query(Referral)
        .filter(
            Referral.referrer_id == referrer_id,
            Referral.status == "activo",
        )
        .count()
    )


def get_referral_promo(db: Session) -> dict:
    settings = get_settings(db)
    return {
        "is_enabled": settings.is_enabled,
        "guayabits_per_referral": settings.guayabits_per_referral,
    }


def generate_referral_link(db: Session, user: User) -> dict:
    settings = get_settings(db)
    if not settings.is_enabled:
        raise HTTPException(status_code=400, detail="El programa de referidos no está activo")

    user.referral_link_generations += 1
    db.commit()
    db.refresh(user)

    rewarded = count_rewarded_referrals(db, user.id)
    active = count_active_referrals(db, user.id)

    return {
        "link": f"{_frontend_base_url()}/login?ref={user.id}",
        "referral_link_generations": user.referral_link_generations,
        "successful_referrals_count": active,
        "rewarded_referrals_count": rewarded,
        "max_referrals": settings.max_referrals_per_user,
        "guayabits_per_referral": settings.guayabits_per_referral,
        "referrals_remaining": max(0, settings.max_referrals_per_user - rewarded),
        "is_enabled": settings.is_enabled,
    }


def attach_referral_on_register(
    db: Session,
    *,
    referrer_id: int | None,
    referred_user_id: int,
) -> None:
    if referrer_id is None:
        return

    settings = get_settings(db)
    if not settings.is_enabled:
        return

    if referrer_id == referred_user_id:
        return

    referrer = db.query(User).filter(User.id == referrer_id).first()
    if referrer is None or referrer.is_admin:
        return

    existing = db.query(Referral).filter(Referral.referred_user_id == referred_user_id).first()
    if existing is not None:
        return

    referral = Referral(
        referrer_id=referrer_id,
        referred_user_id=referred_user_id,
        status="pendiente",
        guayabits_rewarded=0.0,
    )
    db.add(referral)
    db.commit()


def activate_referral_on_email_verify(db: Session, referred_user_id: int) -> None:
    referral = (
        db.query(Referral)
        .filter(
            Referral.referred_user_id == referred_user_id,
            Referral.status == "pendiente",
        )
        .first()
    )
    if referral is None:
        return

    settings = get_settings(db)
    now = datetime.now(timezone.utc)
    referral.status = "activo"
    referral.activated_at = now

    rewarded_count = count_rewarded_referrals(db, referral.referrer_id)
    should_reward = (
        settings.is_enabled
        and rewarded_count < settings.max_referrals_per_user
        and settings.guayabits_per_referral > 0
    )

    if should_reward:
        referred = db.query(User).filter(User.id == referred_user_id).first()
        referred_label = referred.username if referred else str(referred_user_id)
        referral.guayabits_rewarded = settings.guayabits_per_referral
        update_user_balance(
            db,
            referral.referrer_id,
            settings.guayabits_per_referral,
            movement_type="referido",
            concept=f"Referido verificado: @{referred_label}",
            reference_id=referral.id,
        )
    else:
        referral.guayabits_rewarded = 0.0

    db.commit()


def list_user_referrals(db: Session, user_id: int) -> dict:
    settings = get_settings(db)
    referrals = (
        db.query(Referral)
        .filter(Referral.referrer_id == user_id)
        .order_by(Referral.created_at.desc())
        .all()
    )

    items = []
    for referral in referrals:
        referred = db.query(User).filter(User.id == referral.referred_user_id).first()
        if referred is None:
            continue
        items.append(
            {
                "id": referral.id,
                "username": referred.username,
                "email_masked": mask_email(referred.email),
                "status": referral.status,
                "guayabits_rewarded": referral.guayabits_rewarded,
                "created_at": referral.created_at,
                "activated_at": referral.activated_at,
            }
        )

    user = db.query(User).filter(User.id == user_id).first()
    rewarded = count_rewarded_referrals(db, user_id)
    active = count_active_referrals(db, user_id)

    return {
        "referrals": items,
        "referral_link_generations": user.referral_link_generations if user else 0,
        "successful_referrals_count": active,
        "rewarded_referrals_count": rewarded,
        "max_referrals": settings.max_referrals_per_user,
        "guayabits_per_referral": settings.guayabits_per_referral,
        "referrals_remaining": max(0, settings.max_referrals_per_user - rewarded),
        "is_enabled": settings.is_enabled,
        "link": f"{_frontend_base_url()}/login?ref={user_id}" if user else "",
    }


def update_settings(
    db: Session,
    *,
    max_referrals_per_user: int,
    guayabits_per_referral: float,
    is_enabled: bool,
) -> ReferralSettings:
    if max_referrals_per_user < 0:
        raise HTTPException(status_code=400, detail="El máximo de referidos no puede ser negativo")
    if guayabits_per_referral < 0:
        raise HTTPException(status_code=400, detail="Los Guayabits por referido no pueden ser negativos")

    settings = get_settings(db)
    settings.max_referrals_per_user = max_referrals_per_user
    settings.guayabits_per_referral = guayabits_per_referral
    settings.is_enabled = is_enabled
    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


def phone_exists(db: Session, phone: str, *, exclude_user_id: int | None = None) -> bool:
    from app.services.email_validation import normalize_phone

    target = normalize_phone(phone)
    if not target:
        return False

    query = db.query(User.id).filter(
        func.regexp_replace(User.phone, r"\D", "", "g") == target
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.first() is not None


def id_document_exists(db: Session, id_document: str, *, exclude_user_id: int | None = None) -> bool:
    target = id_document.strip()
    if not target:
        return False

    query = db.query(User.id).filter(User.id_document == target)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.first() is not None
