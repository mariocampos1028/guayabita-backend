from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.models_db import RechargePackage
from app.models import RechargePackageCreateRequest, RechargePackageUpdateRequest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_single_popular(
    db: Session,
    *,
    popular: bool,
    package_id: int | None = None,
) -> None:
    if not popular:
        return
    query = db.query(RechargePackage).filter(RechargePackage.popular.is_(True))
    if package_id is not None:
        query = query.filter(RechargePackage.id != package_id)
    existing = query.first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=(
                f'El paquete "{existing.name}" ya está marcado como popular. '
                "Desmarca ese paquete antes de marcar otro como popular."
            ),
        )


def list_all_packages(db: Session) -> list[RechargePackage]:
    return (
        db.query(RechargePackage)
        .options(joinedload(RechargePackage.updated_by))
        .order_by(RechargePackage.price.asc(), RechargePackage.id.asc())
        .all()
    )


def list_active_packages(db: Session) -> list[RechargePackage]:
    return (
        db.query(RechargePackage)
        .filter(RechargePackage.status == "active")
        .order_by(RechargePackage.price.asc(), RechargePackage.id.asc())
        .all()
    )


def get_package(db: Session, package_id: int) -> RechargePackage:
    package = db.query(RechargePackage).filter(RechargePackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return package


def get_popular_package(db: Session) -> RechargePackage | None:
    return db.query(RechargePackage).filter(RechargePackage.popular.is_(True)).first()


def create_package(
    db: Session,
    payload: RechargePackageCreateRequest,
    user_id: int,
) -> RechargePackage:
    _ensure_single_popular(db, popular=payload.popular)
    now = _now()
    package = RechargePackage(
        name=payload.name.strip(),
        price=payload.price,
        guayabits=payload.guayabits,
        status=payload.status,
        popular=payload.popular,
        created_at=now,
        updated_at=now,
        updated_by_id=user_id,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


def update_package(
    db: Session,
    package_id: int,
    payload: RechargePackageUpdateRequest,
    user_id: int,
) -> RechargePackage:
    package = get_package(db, package_id)
    _ensure_single_popular(db, popular=payload.popular, package_id=package_id)

    package.name = payload.name.strip()
    package.price = payload.price
    package.guayabits = payload.guayabits
    package.status = payload.status
    package.popular = payload.popular
    package.updated_at = _now()
    package.updated_by_id = user_id

    db.commit()
    db.refresh(package)
    return package
