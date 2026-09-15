from sqlalchemy.orm import Session

from app.db.models_db import BalanceMovement, User

MOVEMENT_TYPES = frozenset({
    "registro",
    "referido",
    "tienda_regalo",
    "soporte",
    "recarga",
    "partida_entrada",
    "partida_resultado",
    "torneo",
})


def record_movement(
    db: Session,
    *,
    user_id: int,
    movement_type: str,
    concept: str,
    previous_balance: float,
    new_balance: float,
    reference_id: int | None = None,
) -> BalanceMovement | None:
    delta = new_balance - previous_balance
    if abs(delta) < 0.0001:
        return None

    movement = BalanceMovement(
        user_id=user_id,
        movement_type=movement_type,
        concept=concept,
        previous_balance=previous_balance,
        new_balance=new_balance,
        delta=delta,
        reference_id=reference_id,
    )
    db.add(movement)
    return movement


def apply_balance_change(
    db: Session,
    user_id: int,
    *,
    new_balance: float | None = None,
    delta: float | None = None,
    movement_type: str,
    concept: str,
    reference_id: int | None = None,
    commit: bool = True,
) -> User:
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError(f"Tipo de movimiento inválido: {movement_type}")
    if (new_balance is None) == (delta is None):
        raise ValueError("Debe indicarse new_balance o delta, pero no ambos")

    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        raise ValueError(f"Usuario {user_id} no encontrado")

    previous_balance = user.balance
    target_balance = new_balance if new_balance is not None else previous_balance + delta

    if abs(target_balance - previous_balance) < 0.0001:
        return user

    user.balance = target_balance
    record_movement(
        db,
        user_id=user_id,
        movement_type=movement_type,
        concept=concept,
        previous_balance=previous_balance,
        new_balance=target_balance,
        reference_id=reference_id,
    )

    if commit:
        db.commit()
        db.refresh(user)
    return user


def list_user_movements(db: Session, user_id: int, *, limit: int = 200) -> list[BalanceMovement]:
    safe_limit = max(1, min(limit, 500))
    return (
        db.query(BalanceMovement)
        .filter(BalanceMovement.user_id == user_id)
        .order_by(BalanceMovement.created_at.desc(), BalanceMovement.id.desc())
        .limit(safe_limit)
        .all()
    )
