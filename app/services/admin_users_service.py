"""Consulta de usuarios y ajustes auditados de saldo."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.models_db import BalanceAdjustmentLog, User
from app.models import BalanceAdjustmentLogDetailResponse


def _now() -> datetime:
    return datetime.now(timezone.utc)


def search_users(db: Session, query: str, limit: int = 20) -> list[User]:
    term = query.strip()
    if len(term) < 2:
        raise HTTPException(status_code=400, detail="Ingresa al menos 2 caracteres para buscar")

    pattern = f"%{term}%"
    return (
        db.query(User)
        .filter(
            (User.username.ilike(pattern))
            | (User.email.ilike(pattern))
            | (User.first_name.ilike(pattern))
            | (User.last_name.ilike(pattern))
        )
        .order_by(User.username.asc())
        .limit(limit)
        .all()
    )


def get_user_by_id(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def adjust_user_balance(
    db: Session,
    *,
    user_id: int,
    admin_id: int,
    new_balance: float,
    justification: str,
) -> tuple[User, BalanceAdjustmentLog]:
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="El saldo no puede ser negativo")

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="No se puede ajustar el saldo de un administrador")

    previous_balance = user.balance
    if previous_balance == new_balance:
        raise HTTPException(status_code=400, detail="El saldo indicado es igual al actual")

    user.balance = new_balance
    log = BalanceAdjustmentLog(
        user_id=user.id,
        admin_id=admin_id,
        previous_balance=previous_balance,
        new_balance=new_balance,
        delta=new_balance - previous_balance,
        justification=justification.strip(),
        created_at=_now(),
    )
    db.add(log)
    db.commit()
    db.refresh(user)
    db.refresh(log)
    return user, log


def _serialize_balance_log(log: BalanceAdjustmentLog) -> BalanceAdjustmentLogDetailResponse:
    user = log.user
    admin = log.admin
    full_name = f"{user.first_name} {user.last_name}".strip() if user else ""
    return BalanceAdjustmentLogDetailResponse(
        id=log.id,
        user_id=log.user_id,
        admin_id=log.admin_id,
        previous_balance=log.previous_balance,
        new_balance=log.new_balance,
        delta=log.delta,
        justification=log.justification,
        created_at=log.created_at,
        user_username=user.username if user else "—",
        user_full_name=full_name or (user.username if user else "—"),
        admin_username=admin.username if admin else "—",
    )


def list_balance_logs(
    db: Session,
    user_id: int | None = None,
    limit: int = 200,
) -> list[BalanceAdjustmentLogDetailResponse]:
    query = (
        db.query(BalanceAdjustmentLog)
        .options(
            joinedload(BalanceAdjustmentLog.user),
            joinedload(BalanceAdjustmentLog.admin),
        )
        .order_by(BalanceAdjustmentLog.created_at.desc())
    )
    if user_id is not None:
        query = query.filter(BalanceAdjustmentLog.user_id == user_id)
    logs = query.limit(limit).all()
    return [_serialize_balance_log(log) for log in logs]
