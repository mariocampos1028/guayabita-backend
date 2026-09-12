from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import StoreOrder, User
from app.dependencies import get_current_admin, get_current_non_admin
from app.models import (
    GuayabitsRewardCalculationResponse,
    StoreGuayabitsRewardTierRequest,
    StoreGuayabitsRewardTierResponse,
    StoreOrderResponse,
    StoreOrderShippingUpdateRequest,
    StoreOrderStatusUpdateRequest,
    StorePaymentMethodRequest,
    StorePaymentMethodResponse,
    StoreProductAdminResponse,
    StoreProductCreateRequest,
    StoreProductMediaResponse,
    StoreProductResponse,
    StoreProductUpdateRequest,
)
from app.config.store_categories import STORE_CATEGORIES
from app.services import guayabits_tier_service, store_service
from app.services.store_media_service import get_store_object

router = APIRouter(tags=["store"])


@router.get("/store/categories", response_model=list[str])
def product_categories(
    current_user: User = Depends(get_current_non_admin),
):
    _ = current_user
    return list(STORE_CATEGORIES)


@router.get("/store/products", response_model=list[StoreProductResponse])
def products(
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return store_service.list_products(db)


@router.get("/store/products/{product_id}", response_model=StoreProductResponse)
def product_detail(
    product_id: int,
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    return store_service.get_product(db, product_id)


@router.get("/store/payment-methods", response_model=list[StorePaymentMethodResponse])
def payment_methods(
    current_user: User = Depends(get_current_non_admin),
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
    current_user: User = Depends(get_current_non_admin),
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
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    return store_service.list_user_orders(db, current_user.id)


@router.put("/store/orders/{order_id}/shipping", response_model=StoreOrderResponse)
def update_shipping(
    order_id: int,
    payload: StoreOrderShippingUpdateRequest,
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    return store_service.update_order_shipping(db, order_id, current_user.id, payload)


@router.get("/store/orders/{order_id}/receipt")
def user_order_receipt(
    order_id: int,
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    key, _ = store_service.get_user_order_receipt(db, order_id, current_user.id)
    data, content_type = get_store_object(key)
    return Response(data, media_type=content_type)


@router.post("/store/orders/{order_id}/correction", response_model=StoreOrderResponse)
def submit_order_correction(
    order_id: int,
    shipping_address: str = Form(..., min_length=5, max_length=255),
    department: str = Form(..., min_length=2, max_length=80),
    city: str = Form(..., min_length=2, max_length=100),
    reference_point: str | None = Form(default=None, max_length=300),
    customer_notes: str | None = Form(default=None, max_length=1000),
    receipt: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    payload = StoreOrderShippingUpdateRequest(
        shipping_address=shipping_address,
        department=department,
        city=city,
        reference_point=reference_point,
        customer_notes=customer_notes,
    )
    return store_service.submit_order_correction(
        db,
        order_id,
        current_user.id,
        payload,
        receipt,
    )


@router.get("/store/media/{key:path}")
def media(key: str):
    data, content_type = get_store_object(key)
    return Response(data, media_type=content_type)


@router.get("/admin/store/guayabits-tiers", response_model=list[StoreGuayabitsRewardTierResponse])
def admin_guayabits_tiers(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return guayabits_tier_service.list_tiers(db)


@router.post(
    "/admin/store/guayabits-tiers",
    response_model=StoreGuayabitsRewardTierResponse,
    status_code=201,
)
def create_guayabits_tier(
    payload: StoreGuayabitsRewardTierRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return guayabits_tier_service.create_tier(db, payload)


@router.put(
    "/admin/store/guayabits-tiers/{tier_id}",
    response_model=StoreGuayabitsRewardTierResponse,
)
def update_guayabits_tier(
    tier_id: int,
    payload: StoreGuayabitsRewardTierRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return guayabits_tier_service.update_tier(db, tier_id, payload)


@router.delete("/admin/store/guayabits-tiers/{tier_id}", status_code=204)
def delete_guayabits_tier(
    tier_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    guayabits_tier_service.delete_tier(db, tier_id)
    return Response(status_code=204)


@router.get(
    "/admin/store/guayabits-tiers/calculate",
    response_model=GuayabitsRewardCalculationResponse,
)
def calculate_guayabits_reward(
    price: float,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return GuayabitsRewardCalculationResponse(
        price=price,
        guayabits_reward=guayabits_tier_service.calculate_reward(db, price),
    )


@router.get("/admin/store/products", response_model=list[StoreProductAdminResponse])
def admin_products(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.list_products(db, include_inactive=True)


@router.post("/admin/store/products", response_model=StoreProductAdminResponse, status_code=201)
def create_product(
    payload: StoreProductCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.create_product(db, payload, admin.id)


@router.put("/admin/store/products/{product_id}", response_model=StoreProductAdminResponse)
def update_product(
    product_id: int,
    payload: StoreProductUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.update_product(db, product_id, payload, admin.id)


@router.delete("/admin/store/products/{product_id}", response_model=StoreProductAdminResponse)
def archive_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.archive_product(db, product_id, admin.id)


@router.post("/admin/store/products/{product_id}/activate", response_model=StoreProductAdminResponse)
def activate_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return store_service.activate_product(db, product_id, admin.id)


@router.delete("/admin/store/products/{product_id}/permanent", status_code=204)
def delete_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    store_service.delete_product(db, product_id)
    return Response(status_code=204)


@router.post(
    "/admin/store/products/{product_id}/media",
    response_model=StoreProductMediaResponse,
    status_code=201,
)
def add_media(
    product_id: int,
    sort_order: int = Form(default=0),
    is_primary: bool = Form(default=False),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.add_product_media(
        db, product_id, file, sort_order, is_primary=is_primary
    )


@router.post(
    "/admin/store/products/{product_id}/media/batch",
    response_model=list[StoreProductMediaResponse],
    status_code=201,
)
def add_media_batch(
    product_id: int,
    files: list[UploadFile] = File(...),
    primary_index: int = Form(default=-1),
    start_sort_order: int = Form(default=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    primary = primary_index if primary_index >= 0 else None
    return store_service.add_product_media_batch(
        db,
        product_id,
        files,
        primary_index=primary,
        start_sort_order=start_sort_order,
    )


@router.patch(
    "/admin/store/products/{product_id}/media/{media_id}/primary",
    response_model=StoreProductMediaResponse,
)
def set_primary_media(
    product_id: int,
    media_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.set_primary_media(db, product_id, media_id)


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
