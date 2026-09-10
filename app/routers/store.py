from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import StoreOrder, User
from app.dependencies import get_current_admin, get_current_user
from app.models import (
    StoreOrderResponse,
    StoreOrderShippingUpdateRequest,
    StoreOrderStatusUpdateRequest,
    StorePaymentMethodRequest,
    StorePaymentMethodResponse,
    StoreProductCreateRequest,
    StoreProductMediaResponse,
    StoreProductResponse,
    StoreProductUpdateRequest,
)
from app.services import store_service
from app.services.store_media_service import get_store_object

router = APIRouter(tags=["store"])


@router.get("/store/products", response_model=list[StoreProductResponse])
def products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return store_service.list_products(db)


@router.get("/store/products/{product_id}", response_model=StoreProductResponse)
def product_detail(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return store_service.get_product(db, product_id)


@router.get("/store/payment-methods", response_model=list[StorePaymentMethodResponse])
def payment_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return store_service.list_payment_methods(db)


@router.post("/store/orders", response_model=StoreOrderResponse, status_code=201)
def create_order(
    product_id: int = Form(...),
    payment_type: str = Form(...),
    shipping_address: str = Form(..., min_length=5, max_length=255),
    department: str = Form(..., min_length=2, max_length=80),
    city: str = Form(..., min_length=2, max_length=100),
    payment_method_id: int | None = Form(default=None),
    reference_point: str | None = Form(default=None, max_length=300),
    customer_notes: str | None = Form(default=None, max_length=1000),
    receipt: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return store_service.create_order(
        db,
        current_user,
        product_id=product_id,
        payment_type=payment_type,
        payment_method_id=payment_method_id,
        shipping_address=shipping_address,
        department=department,
        city=city,
        reference_point=reference_point,
        customer_notes=customer_notes,
        receipt=receipt,
    )


@router.get("/store/orders/me", response_model=list[StoreOrderResponse])
def my_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return store_service.list_user_orders(db, current_user.id)


@router.put("/store/orders/{order_id}/shipping", response_model=StoreOrderResponse)
def update_shipping(
    order_id: int,
    payload: StoreOrderShippingUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return store_service.update_order_shipping(db, order_id, current_user.id, payload)


@router.get("/store/media/{key:path}")
def media(key: str):
    data, content_type = get_store_object(key)
    return Response(data, media_type=content_type)


@router.get("/admin/store/products", response_model=list[StoreProductResponse])
def admin_products(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.list_products(db, include_inactive=True)


@router.post("/admin/store/products", response_model=StoreProductResponse, status_code=201)
def create_product(
    payload: StoreProductCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.create_product(db, payload, admin.id)


@router.put("/admin/store/products/{product_id}", response_model=StoreProductResponse)
def update_product(
    product_id: int,
    payload: StoreProductUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.update_product(db, product_id, payload, admin.id)


@router.delete("/admin/store/products/{product_id}", response_model=StoreProductResponse)
def archive_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.archive_product(db, product_id, admin.id)


@router.post(
    "/admin/store/products/{product_id}/media",
    response_model=StoreProductMediaResponse,
    status_code=201,
)
def add_media(
    product_id: int,
    sort_order: int = Form(default=0),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.add_product_media(db, product_id, file, sort_order)


@router.delete("/admin/store/products/{product_id}/media/{media_id}", status_code=204)
def delete_media(
    product_id: int,
    media_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    store_service.delete_product_media(db, product_id, media_id)
    return Response(status_code=204)


@router.get(
    "/admin/store/payment-methods",
    response_model=list[StorePaymentMethodResponse],
)
def admin_payment_methods(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.list_payment_methods(db, include_inactive=True)


@router.post(
    "/admin/store/payment-methods",
    response_model=StorePaymentMethodResponse,
    status_code=201,
)
def create_payment_method(
    payload: StorePaymentMethodRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.save_payment_method(db, payload, admin.id)


@router.put(
    "/admin/store/payment-methods/{method_id}",
    response_model=StorePaymentMethodResponse,
)
def update_payment_method(
    method_id: int,
    payload: StorePaymentMethodRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.save_payment_method(db, payload, admin.id, method_id)


@router.get("/admin/store/orders", response_model=list[StoreOrderResponse])
def admin_orders(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.list_all_orders(db)


@router.get("/admin/store/orders/{order_id}/receipt")
def order_receipt(
    order_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    order = db.query(StoreOrder).filter(StoreOrder.id == order_id).first()
    if not order or not order.payment_receipt_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    data, content_type = get_store_object(order.payment_receipt_key)
    return Response(data, media_type=content_type)


@router.patch("/admin/store/orders/{order_id}/status", response_model=StoreOrderResponse)
def update_status(
    order_id: int,
    payload: StoreOrderStatusUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.update_order_status(db, order_id, payload)
