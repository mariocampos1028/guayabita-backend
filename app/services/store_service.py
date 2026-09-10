from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.db.models_db import (
    StoreOrder,
    StorePaymentMethod,
    StoreProduct,
    StoreProductMedia,
    User,
)
from app.models import (
    StoreOrderShippingUpdateRequest,
    StoreOrderStatusUpdateRequest,
    StorePaymentMethodRequest,
    StoreProductCreateRequest,
    StoreProductUpdateRequest,
)
from app.services.store_media_service import (
    delete_store_object,
    payment_receipt_url,
    upload_payment_receipt,
    upload_product_media,
)

EDITABLE_ORDER_STATUSES = {"en_validacion", "en_proceso"}
ORDER_STATUSES = {
    "en_validacion",
    "en_proceso",
    "en_alistamiento",
    "en_reparto",
    "entregado",
    "rechazado",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reference() -> str:
    return f"PED-{_now():%Y%m%d}-{secrets.token_hex(4).upper()}"


def list_products(db: Session, *, include_inactive: bool = False) -> list[StoreProduct]:
    query = db.query(StoreProduct).options(joinedload(StoreProduct.media))
    if not include_inactive:
        query = query.filter(StoreProduct.status == "active")
    return query.order_by(StoreProduct.created_at.desc()).all()


def get_product(db: Session, product_id: int, *, allow_inactive: bool = False) -> StoreProduct:
    product = (
        db.query(StoreProduct)
        .options(joinedload(StoreProduct.media))
        .filter(StoreProduct.id == product_id)
        .first()
    )
    if not product or (not allow_inactive and product.status != "active"):
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


def create_product(
    db: Session, payload: StoreProductCreateRequest, admin_id: int
) -> StoreProduct:
    product = StoreProduct(**payload.model_dump(), updated_by_id=admin_id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return get_product(db, product.id, allow_inactive=True)


def update_product(
    db: Session, product_id: int, payload: StoreProductUpdateRequest, admin_id: int
) -> StoreProduct:
    product = get_product(db, product_id, allow_inactive=True)
    for key, value in payload.model_dump().items():
        setattr(product, key, value)
    product.updated_by_id = admin_id
    product.updated_at = _now()
    db.commit()
    return get_product(db, product.id, allow_inactive=True)


def archive_product(db: Session, product_id: int, admin_id: int) -> StoreProduct:
    product = get_product(db, product_id, allow_inactive=True)
    product.status = "inactive"
    product.updated_by_id = admin_id
    product.updated_at = _now()
    db.commit()
    return get_product(db, product.id, allow_inactive=True)


def add_product_media(
    db: Session, product_id: int, file: UploadFile, sort_order: int
) -> StoreProductMedia:
    get_product(db, product_id, allow_inactive=True)
    media_type, key, url = upload_product_media(product_id, file)
    media = StoreProductMedia(
        product_id=product_id,
        media_type=media_type,
        object_key=key,
        url=url,
        sort_order=sort_order,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def delete_product_media(db: Session, product_id: int, media_id: int) -> None:
    media = (
        db.query(StoreProductMedia)
        .filter(
            StoreProductMedia.id == media_id,
            StoreProductMedia.product_id == product_id,
        )
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    delete_store_object(media.object_key)
    db.delete(media)
    db.commit()


def list_payment_methods(db: Session, *, include_inactive: bool = False) -> list[StorePaymentMethod]:
    query = db.query(StorePaymentMethod)
    if not include_inactive:
        query = query.filter(StorePaymentMethod.is_active.is_(True))
    return query.order_by(StorePaymentMethod.method_type, StorePaymentMethod.id).all()


def save_payment_method(
    db: Session,
    payload: StorePaymentMethodRequest,
    admin_id: int,
    method_id: int | None = None,
) -> StorePaymentMethod:
    if method_id:
        method = db.query(StorePaymentMethod).filter(StorePaymentMethod.id == method_id).first()
        if not method:
            raise HTTPException(status_code=404, detail="Método de pago no encontrado")
        for key, value in payload.model_dump().items():
            setattr(method, key, value)
    else:
        method = StorePaymentMethod(**payload.model_dump())
        db.add(method)
    method.updated_by_id = admin_id
    method.updated_at = _now()
    db.commit()
    db.refresh(method)
    return method


def create_order(
    db: Session,
    user: User,
    *,
    product_id: int,
    payment_type: str,
    payment_method_id: int | None,
    shipping_address: str,
    department: str,
    city: str,
    reference_point: str | None,
    customer_notes: str | None,
    receipt: UploadFile | None,
) -> StoreOrder:
    product = get_product(db, product_id)
    if payment_type == "contraentrega":
        if not product.allow_cash_on_delivery:
            raise HTTPException(status_code=400, detail="Este producto no permite pago contraentrega")
        method = None
        status = "en_proceso"
    elif payment_type == "directo":
        if not product.allow_direct_payment:
            raise HTTPException(status_code=400, detail="Este producto no permite pago directo")
        method = (
            db.query(StorePaymentMethod)
            .filter(
                StorePaymentMethod.id == payment_method_id,
                StorePaymentMethod.is_active.is_(True),
            )
            .first()
        )
        if not method:
            raise HTTPException(status_code=400, detail="Selecciona un método de pago válido")
        if receipt is None:
            raise HTTPException(status_code=400, detail="Debes cargar el comprobante de pago")
        status = "en_validacion"
    else:
        raise HTTPException(status_code=400, detail="Forma de pago inválida")

    required_profile = {
        "nombre": user.first_name,
        "apellido": user.last_name,
        "correo": user.email,
        "teléfono": user.phone,
    }
    missing = [label for label, value in required_profile.items() if not (value or "").strip()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Completa en tu perfil: {', '.join(missing)}",
        )

    reference = _reference()
    receipt_key = None
    if receipt is not None:
        receipt_key = upload_payment_receipt(reference, receipt)

    order = StoreOrder(
        reference=reference,
        user_id=user.id,
        product_id=product.id,
        product_name=product.name,
        product_price=product.price,
        guayabits_reward=product.guayabits_reward,
        customer_first_name=user.first_name,
        customer_last_name=user.last_name,
        customer_email=user.email,
        customer_phone=user.phone,
        shipping_address=shipping_address.strip(),
        department=department.strip(),
        city=city.strip(),
        reference_point=(reference_point or "").strip() or None,
        customer_notes=(customer_notes or "").strip() or None,
        payment_type=payment_type,
        payment_method_id=method.id if method else None,
        payment_method_name=method.display_name if method else "Pago contraentrega",
        payment_receipt_key=receipt_key,
        status=status,
    )
    db.add(order)
    db.flush()
    if receipt_key:
        order.payment_receipt_url = payment_receipt_url(order.id)
    db.commit()
    db.refresh(order)
    return order


def list_user_orders(db: Session, user_id: int) -> list[StoreOrder]:
    return (
        db.query(StoreOrder)
        .filter(StoreOrder.user_id == user_id)
        .order_by(StoreOrder.created_at.desc())
        .all()
    )


def update_order_shipping(
    db: Session, order_id: int, user_id: int, payload: StoreOrderShippingUpdateRequest
) -> StoreOrder:
    order = (
        db.query(StoreOrder)
        .filter(StoreOrder.id == order_id, StoreOrder.user_id == user_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.status not in EDITABLE_ORDER_STATUSES:
        raise HTTPException(status_code=409, detail="El pedido ya no permite editar el envío")
    for key, value in payload.model_dump().items():
        setattr(order, key, value.strip() if isinstance(value, str) else value)
    order.updated_at = _now()
    db.commit()
    db.refresh(order)
    return order


def list_all_orders(db: Session) -> list[StoreOrder]:
    return db.query(StoreOrder).order_by(StoreOrder.created_at.desc()).all()


def update_order_status(
    db: Session, order_id: int, payload: StoreOrderStatusUpdateRequest
) -> StoreOrder:
    order = (
        db.query(StoreOrder)
        .filter(StoreOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if payload.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido")

    should_credit = (
        order.payment_type == "directo" and payload.status == "en_proceso"
    ) or (
        order.payment_type == "contraentrega" and payload.status == "entregado"
    )
    if should_credit and not order.guayabits_credited:
        user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
        if user:
            user.balance += order.guayabits_reward * order.quantity
            order.guayabits_credited = True

    order.status = payload.status
    order.admin_observations = payload.admin_observations
    order.updated_at = _now()
    db.commit()
    db.refresh(order)
    return order
