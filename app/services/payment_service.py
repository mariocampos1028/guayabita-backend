from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models_db import RechargePackage, RechargePurchase, User
from app.services import auth_service, wompi_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_purchase_response(purchase: RechargePurchase):
    from app.models import PurchaseResponse

    return PurchaseResponse.model_validate(purchase)


def create_checkout(db: Session, user: User, package_id: int) -> dict:
    try:
        wompi_service.ensure_wompi_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    package = db.query(RechargePackage).filter(RechargePackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    if package.status != "active":
        raise HTTPException(status_code=400, detail="El paquete seleccionado no está disponible")

    purchase = RechargePurchase(
        user_id=user.id,
        package_id=package.id,
        package_name=package.name,
        price=package.price,
        guayabits=package.guayabits,
        reference=wompi_service.generate_placeholder_reference(),
        status="pending",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(purchase)
    db.flush()

    purchase.reference = wompi_service.generate_reference(purchase.id)
    db.commit()
    db.refresh(purchase)

    amount_in_cents = wompi_service.price_to_cents(package.price)
    signature = wompi_service.build_integrity_signature(purchase.reference, amount_in_cents)
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username

    return {
        "purchase_id": purchase.id,
        "reference": purchase.reference,
        "public_key": wompi_service.WOMPI_PUBLIC_KEY,
        "currency": "COP",
        "amount_in_cents": amount_in_cents,
        "signature": signature,
        "redirect_url": wompi_service.resolve_redirect_url(),
        "customer_email": user.email,
        "customer_full_name": full_name,
    }


def get_purchase_for_user(db: Session, purchase_id: int, user_id: int) -> RechargePurchase:
    purchase = (
        db.query(RechargePurchase)
        .filter(RechargePurchase.id == purchase_id, RechargePurchase.user_id == user_id)
        .first()
    )
    if not purchase:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    return purchase


def cancel_purchase(db: Session, purchase_id: int, user_id: int) -> RechargePurchase:
    purchase = get_purchase_for_user(db, purchase_id, user_id)
    if purchase.status != "pending":
        return purchase
    purchase.status = "cancelled"
    purchase.updated_at = _now()
    db.commit()
    db.refresh(purchase)
    return purchase


def list_user_purchases(db: Session, user_id: int, limit: int = 20) -> list[RechargePurchase]:
    return (
        db.query(RechargePurchase)
        .filter(RechargePurchase.user_id == user_id)
        .order_by(RechargePurchase.created_at.desc())
        .limit(limit)
        .all()
    )


def get_purchase_by_reference(db: Session, reference: str) -> RechargePurchase | None:
    return db.query(RechargePurchase).filter(RechargePurchase.reference == reference).first()


def _map_wompi_status(wompi_status: str) -> str:
    status = wompi_status.upper()
    if status == "APPROVED":
        return "approved"
    if status in {"DECLINED", "ERROR"}:
        return "declined" if status == "DECLINED" else "error"
    if status == "VOIDED":
        return "voided"
    return "pending"


def _apply_approved_purchase(db: Session, purchase: RechargePurchase, transaction: dict) -> None:
    if purchase.status == "approved":
        return
    purchase.status = "approved"
    purchase.wompi_transaction_id = transaction.get("id")
    purchase.wompi_status = transaction.get("status")
    purchase.wompi_payment_method = transaction.get("payment_method_type")
    purchase.updated_at = _now()
    auth_service.update_user_balance(db, purchase.user_id, purchase.guayabits)


def process_transaction_update(db: Session, transaction: dict) -> RechargePurchase | None:
    reference = transaction.get("reference")
    if not reference:
        return None

    purchase = get_purchase_by_reference(db, reference)
    if not purchase:
        return None

    wompi_status = (transaction.get("status") or "").upper()
    purchase.wompi_transaction_id = transaction.get("id") or purchase.wompi_transaction_id
    purchase.wompi_status = transaction.get("status")
    purchase.wompi_payment_method = transaction.get("payment_method_type")
    purchase.updated_at = _now()

    if wompi_status == "APPROVED":
        _apply_approved_purchase(db, purchase, transaction)
    elif wompi_status in {"DECLINED", "ERROR", "VOIDED"}:
        purchase.status = _map_wompi_status(wompi_status)
        db.commit()
        db.refresh(purchase)
    else:
        db.commit()
        db.refresh(purchase)

    return purchase


def handle_wompi_event(db: Session, event: dict) -> None:
    if event.get("event") != "transaction.updated":
        return
    if not wompi_service.verify_event_checksum(event):
        raise HTTPException(status_code=401, detail="Firma de evento Wompi inválida")

    transaction = (event.get("data") or {}).get("transaction") or {}
    process_transaction_update(db, transaction)
