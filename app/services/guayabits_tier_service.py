from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models_db import StoreGuayabitsRewardTier
from app.models import StoreGuayabitsRewardTierRequest


def _ranges_overlap(from_a: float, to_a: float, from_b: float, to_b: float) -> bool:
    return from_a <= to_b and from_b <= to_a


def _validate_tier_bounds(amount_from: float, amount_to: float) -> None:
    if amount_from < 0:
        raise HTTPException(status_code=400, detail="El monto inicial no puede ser negativo")
    if amount_to <= amount_from:
        raise HTTPException(status_code=400, detail="El monto final debe ser mayor al inicial")


def _ensure_no_overlap(
    db: Session,
    amount_from: float,
    amount_to: float,
    *,
    exclude_id: int | None = None,
) -> None:
    query = db.query(StoreGuayabitsRewardTier)
    if exclude_id is not None:
        query = query.filter(StoreGuayabitsRewardTier.id != exclude_id)
    for tier in query.all():
        if _ranges_overlap(amount_from, amount_to, tier.amount_from, tier.amount_to):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El rango se solapa con ${tier.amount_from:,.0f}–${tier.amount_to:,.0f}"
                ),
            )


def list_tiers(db: Session) -> list[StoreGuayabitsRewardTier]:
    return (
        db.query(StoreGuayabitsRewardTier)
        .order_by(StoreGuayabitsRewardTier.amount_from.asc())
        .all()
    )


def create_tier(db: Session, payload: StoreGuayabitsRewardTierRequest) -> StoreGuayabitsRewardTier:
    _validate_tier_bounds(payload.amount_from, payload.amount_to)
    _ensure_no_overlap(db, payload.amount_from, payload.amount_to)
    tier = StoreGuayabitsRewardTier(**payload.model_dump())
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


def update_tier(
    db: Session, tier_id: int, payload: StoreGuayabitsRewardTierRequest
) -> StoreGuayabitsRewardTier:
    tier = db.query(StoreGuayabitsRewardTier).filter(StoreGuayabitsRewardTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Rango no encontrado")
    _validate_tier_bounds(payload.amount_from, payload.amount_to)
    _ensure_no_overlap(db, payload.amount_from, payload.amount_to, exclude_id=tier_id)
    for key, value in payload.model_dump().items():
        setattr(tier, key, value)
    db.commit()
    db.refresh(tier)
    return tier


def delete_tier(db: Session, tier_id: int) -> None:
    tier = db.query(StoreGuayabitsRewardTier).filter(StoreGuayabitsRewardTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Rango no encontrado")
    db.delete(tier)
    db.commit()


def calculate_reward(db: Session, price: float) -> float:
    if price <= 0:
        return 0.0
    tier = (
        db.query(StoreGuayabitsRewardTier)
        .filter(
            StoreGuayabitsRewardTier.amount_from <= price,
            StoreGuayabitsRewardTier.amount_to >= price,
        )
        .order_by(StoreGuayabitsRewardTier.amount_from.desc())
        .first()
    )
    return tier.guayabits_reward if tier else 0.0
