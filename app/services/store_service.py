from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile
from sqlalchemy import desc
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
    upload_payment_receipt,
    upload_product_media,
)

EDITABLE_ORDER_STATUSES = {"en_validacion", "en_proceso", "devuelto_correccion"}
DIRECT_PAYMENT_EDIT_STATUSES = {"en_validacion", "devuelto_correccion"}
CLOSED_ORDER_STATUSES = {"entregado", "rechazado"}
ORDER_STATUSES = {
    "en_validacion",
    "en_proceso",
    "en_alistamiento",
    "en_reparto",
    "entregado",
    "rechazado",
    "devuelto_correccion",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reference() -> str:
    return f"PED-{_now():%Y%m%d}-{secrets.token_hex(4).upper()}"


def _credit_order_guayabits(db: Session, order: StoreOrder) -> None:
    if order.guayabits_credited or order.guayabits_reward <= 0:
        return
    user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
    if not user or user.is_admin:
        return

    from app.services.balance_movement_service import apply_balance_change

    amount = order.guayabits_reward * order.quantity
    apply_balance_change(
        db,
        user.id,
        delta=amount,
        movement_type="tienda_regalo",
        concept=f"Regalo por compra en tienda — {order.product_name}",
        reference_id=order.id,
        commit=False,
    )
    order.guayabits_credited = True


def _user_receipt_url(order_id: int) -> str:
    return f"/store/orders/{order_id}/receipt"


def _order_allows_shipping_edit(order: StoreOrder) -> bool:
    return (
        not order.guayabits_credited
        and order.status in EDITABLE_ORDER_STATUSES
    )


def _get_user_order(db: Session, order_id: int, user_id: int) -> StoreOrder:
    order = (
        db.query(StoreOrder)
        .filter(StoreOrder.id == order_id, StoreOrder.user_id == user_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order


def list_products(db: Session, *, include_inactive: bool = False) -> list[StoreProduct]:
    query = db.query(StoreProduct).options(joinedload(StoreProduct.media))
    if not include_inactive:
        query = query.filter(StoreProduct.status == "active")
    return query.order_by(
        desc(StoreProduct.is_popular),
        StoreProduct.created_at.desc(),
    ).all()


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


def activate_product(db: Session, product_id: int, admin_id: int) -> StoreProduct:
    product = get_product(db, product_id, allow_inactive=True)
    product.status = "active"
    product.updated_by_id = admin_id
    product.updated_at = _now()
    db.commit()
    return get_product(db, product.id, allow_inactive=True)


def delete_product(db: Session, product_id: int) -> None:
    product = get_product(db, product_id, allow_inactive=True)
    for media in list(product.media):
        delete_store_object(media.object_key)
    db.query(StoreOrder).filter(StoreOrder.product_id == product_id).update(
        {StoreOrder.product_id: None},
        synchronize_session=False,
    )
    db.delete(product)
    db.commit()


def _product_media_query(db: Session, product_id: int):
    return db.query(StoreProductMedia).filter(StoreProductMedia.product_id == product_id)


def _ensure_primary_media(db: Session, product_id: int) -> None:
    media_items = _product_media_query(db, product_id).order_by(
        StoreProductMedia.sort_order,
        StoreProductMedia.id,
    ).all()
    if not media_items:
        return
    if any(item.is_primary for item in media_items):
        return
    preferred = next((item for item in media_items if item.media_type == "image"), media_items[0])
    preferred.is_primary = True
    db.commit()


def add_product_media(
    db: Session,
    product_id: int,
    file: UploadFile,
    sort_order: int,
    *,
    is_primary: bool = False,
    auto_primary_if_empty: bool = True,
    commit: bool = True,
) -> StoreProductMedia:
    get_product(db, product_id, allow_inactive=True)
    media_type, key, url = upload_product_media(product_id, file)
    existing = _product_media_query(db, product_id).count()
    should_be_primary = is_primary or (auto_primary_if_empty and existing == 0)
    if should_be_primary:
        _product_media_query(db, product_id).update({StoreProductMedia.is_primary: False})
    media = StoreProductMedia(
        product_id=product_id,
        media_type=media_type,
        object_key=key,
        url=url,
        sort_order=sort_order,
        is_primary=should_be_primary,
    )
    db.add(media)
    if commit:
        db.commit()
        db.refresh(media)
    else:
        db.flush()
    return media


def add_product_media_batch(
    db: Session,
    product_id: int,
    files: list[UploadFile],
    *,
    primary_index: int | None = None,
    start_sort_order: int = 0,
) -> list[StoreProductMedia]:
    if not files:
        return []
    get_product(db, product_id, allow_inactive=True)
    existing = _product_media_query(db, product_id).count()
    has_primary = _product_media_query(db, product_id).filter(
        StoreProductMedia.is_primary.is_(True),
    ).count() > 0
    created: list[StoreProductMedia] = []
    for index, file in enumerate(files):
        should_be_primary = (
            (primary_index == index)
            or (primary_index is None and index == 0 and not has_primary and existing == 0)
        )
        if should_be_primary and (has_primary or created):
            _product_media_query(db, product_id).update({StoreProductMedia.is_primary: False})
        media = add_product_media(
            db,
            product_id,
            file,
            start_sort_order + index,
            is_primary=should_be_primary,
            auto_primary_if_empty=False,
            commit=False,
        )
        if should_be_primary:
            has_primary = True
        created.append(media)
    db.commit()
    for media in created:
        db.refresh(media)
    return created


def set_primary_media(db: Session, product_id: int, media_id: int) -> StoreProductMedia:
    media = (
        _product_media_query(db, product_id)
        .filter(StoreProductMedia.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    _product_media_query(db, product_id).update({StoreProductMedia.is_primary: False})
    media.is_primary = True
    db.commit()
    db.refresh(media)
    return media


def delete_product_media(db: Session, product_id: int, media_id: int) -> None:
    media = (
        _product_media_query(db, product_id)
        .filter(StoreProductMedia.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    was_primary = media.is_primary
    delete_store_object(media.object_key)
    db.delete(media)
    db.commit()
    if was_primary:
        _ensure_primary_media(db, product_id)


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
    if user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Los administradores no pueden realizar compras en la tienda",
        )

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
        order.payment_receipt_url = _user_receipt_url(order.id)
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


def get_user_order_receipt(db: Session, order_id: int, user_id: int) -> tuple[str, StoreOrder]:
    order = _get_user_order(db, order_id, user_id)
    if not order.payment_receipt_key:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    return order.payment_receipt_key, order


def update_order_shipping(
    db: Session, order_id: int, user_id: int, payload: StoreOrderShippingUpdateRequest
) -> StoreOrder:
    order = _get_user_order(db, order_id, user_id)
    if not _order_allows_shipping_edit(order):
        raise HTTPException(
            status_code=409,
            detail="Este pedido ya fue cerrado o ya recibió los Guayabits de regalo",
        )
    for key, value in payload.model_dump().items():
        setattr(order, key, value.strip() if isinstance(value, str) else value)
    order.updated_at = _now()
    db.commit()
    db.refresh(order)
    return order


def submit_order_correction(
    db: Session,
    order_id: int,
    user_id: int,
    payload: StoreOrderShippingUpdateRequest,
    receipt: UploadFile | None,
) -> StoreOrder:
    order = _get_user_order(db, order_id, user_id)
    if order.guayabits_credited:
        raise HTTPException(status_code=409, detail="Este pedido ya fue cerrado")
    if order.payment_type != "directo":
        raise HTTPException(status_code=400, detail="Solo aplica a pedidos con pago directo")
    if order.status not in DIRECT_PAYMENT_EDIT_STATUSES:
        raise HTTPException(status_code=409, detail="Este pedido ya no permite correcciones")

    for key, value in payload.model_dump().items():
        setattr(order, key, value.strip() if isinstance(value, str) else value)

    requires_resubmit = order.status == "devuelto_correccion"
    if requires_resubmit and receipt is None:
        raise HTTPException(
            status_code=400,
            detail="Debes adjuntar un comprobante legible para reenviar la solicitud",
        )

    if receipt is not None:
        if order.payment_receipt_key:
            delete_store_object(order.payment_receipt_key)
        receipt_key = upload_payment_receipt(order.reference, receipt)
        order.payment_receipt_key = receipt_key
        order.payment_receipt_url = _user_receipt_url(order.id)

    if requires_resubmit:
        order.status = "en_validacion"

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

    if payload.status == "devuelto_correccion":
        if order.payment_type != "directo":
            raise HTTPException(
                status_code=400,
                detail="Solo los pedidos con pago directo pueden devolverse a corrección",
            )
        if not (payload.admin_observations or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Debes indicar al cliente qué debe corregir",
            )

    if order.guayabits_credited and order.status in CLOSED_ORDER_STATUSES:
        if payload.status != order.status:
            raise HTTPException(
                status_code=409,
                detail="Este pedido ya fue cerrado y no puede reabrirse ni cambiar de estado",
            )
        order.admin_observations = payload.admin_observations
        order.updated_at = _now()
        db.commit()
        db.refresh(order)
        return order

    if payload.status == "entregado":
        _credit_order_guayabits(db, order)

    order.status = payload.status
    order.admin_observations = payload.admin_observations
    order.updated_at = _now()
    db.commit()
    db.refresh(order)
    return order
