"""Consulta de usuarios y ajustes auditados de saldo."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, aliased, joinedload

from app.db.models_db import BalanceAdjustmentLog, User
from app.models import BalanceAdjustmentLogDetailResponse


def _now() -> datetime:
    return datetime.now(timezone.utc)


def search_users_page(db: Session, query: str, *, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
    term = query.strip()
    if len(term) < 2:
        raise HTTPException(status_code=400, detail="Ingresa al menos 2 caracteres para buscar")

    pattern = f"%{term}%"
    filtered = db.query(User).filter(
        (User.username.ilike(pattern))
        | (User.email.ilike(pattern))
        | (User.first_name.ilike(pattern))
        | (User.last_name.ilike(pattern))
    )
    total = filtered.order_by(None).count()
    items = (
        filtered.order_by(User.username.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


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

    from app.services.balance_movement_service import record_movement

    user.balance = new_balance
    record_movement(
        db,
        user_id=user.id,
        movement_type="soporte",
        concept=f"Ajuste por soporte: {justification.strip()}",
        previous_balance=previous_balance,
        new_balance=new_balance,
        reference_id=None,
    )
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


def list_balance_logs_page(
    db: Session,
    user_id: int | None = None,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[BalanceAdjustmentLogDetailResponse], int]:
    query = db.query(BalanceAdjustmentLog)
    if user_id is not None:
        query = query.filter(BalanceAdjustmentLog.user_id == user_id)

    term = (q or "").strip()
    if term:
        subject = aliased(User)
        admin_user = aliased(User)
        pattern = f"%{term}%"
        query = (
            query.join(subject, BalanceAdjustmentLog.user_id == subject.id)
            .join(admin_user, BalanceAdjustmentLog.admin_id == admin_user.id)
            .filter(
                subject.username.ilike(pattern)
                | subject.first_name.ilike(pattern)
                | subject.last_name.ilike(pattern)
                | admin_user.username.ilike(pattern)
            )
        )

    total = query.order_by(None).count()
    logs = (
        query.options(
            joinedload(BalanceAdjustmentLog.user),
            joinedload(BalanceAdjustmentLog.admin),
        )
        .order_by(BalanceAdjustmentLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_serialize_balance_log(log) for log in logs], total
