from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import StoreOrder, User
from app.dependencies import get_current_admin, get_current_non_admin
from app.emails import (
    send_order_created_admin_email,
    send_order_created_email,
    send_order_status_changed_email,
)
from app.models import (
    GuayabitsRewardCalculationResponse,
    StoreGuayabitsRewardTierRequest,
    StoreGuayabitsRewardTierResponse,
    StoreOrderResponse,
    StoreOrderPageResponse,
    StoreOrderShippingUpdateRequest,
    StoreOrderStatusUpdateRequest,
    StorePaymentMethodRequest,
    StorePaymentMethodResponse,
    StoreProductAdminResponse,
    StoreProductCreateRequest,
    StoreProductMediaResponse,
    StoreProductResponse,
    StoreProductPageResponse,
    StoreProductAdminPageResponse,
    StoreProductUpdateRequest,
)
from app.config.store_categories import STORE_CATEGORIES
from app.services import guayabits_tier_service, store_service
from app.services import rate_limit_service
from app.services import response_cache_service
from app.services.r2_storage_service import CACHE_CONTROL_IMMUTABLE, CACHE_CONTROL_PRIVATE
from app.services.store_media_service import get_store_object

router = APIRouter(tags=["store"])

PUBLIC_PRODUCTS_CACHE_KEY = "cache:store:products:active:v1"
PUBLIC_PAYMENT_METHODS_CACHE_KEY = "cache:store:payment-methods:active:v1"
PUBLIC_STORE_CACHE_TTL = 60

# Motivo de devolución/rechazo visible en el correo al comprador únicamente
# para estos estados — en el resto, admin_observations es una nota interna.
_STATUS_REASON_VISIBLE = {"devuelto_correccion", "rechazado"}


def _dispatch_order_created_emails(
    customer_email: str,
    customer_first_name: str,
    reference: str,
    product_name: str,
    product_price: float,
    payment_type: str,
    status: str,
    order_id: int,
) -> None:
    status_label = store_service.ORDER_STATUS_LABELS_ES.get(status, status)
    send_order_created_email(
        to=customer_email,
        username=customer_first_name,
        reference=reference,
        product_name=product_name,
        product_price=product_price,
        payment_type=payment_type,
        status_label=status_label,
    )
    customer_name = customer_first_name
    send_order_created_admin_email(
        customer_name=customer_name,
        customer_email=customer_email,
        reference=reference,
        product_name=product_name,
        product_price=product_price,
        payment_type_label=store_service.PAYMENT_TYPE_LABELS_ES.get(payment_type, payment_type),
        status_label=status_label,
        order_id=order_id,
    )


def _dispatch_order_status_changed_email(
    customer_email: str,
    customer_first_name: str,
    reference: str,
    product_name: str,
    status: str,
    reason: str | None,
) -> None:
    send_order_status_changed_email(
        to=customer_email,
        username=customer_first_name,
        reference=reference,
        product_name=product_name,
        status_label=store_service.ORDER_STATUS_LABELS_ES.get(status, status),
        reason=reason if status in _STATUS_REASON_VISIBLE else None,
    )


@router.get("/store/categories", response_model=list[str])
def product_categories():
    return list(STORE_CATEGORIES)


@router.get("/store/products", response_model=list[StoreProductResponse])
def products(db: Session = Depends(get_db)):
    cached = response_cache_service.get_json(PUBLIC_PRODUCTS_CACHE_KEY)
    if cached is not response_cache_service.CACHE_MISS:
        return cached
    items = [StoreProductResponse.model_validate(item).model_dump(mode="json") for item in store_service.list_products(db)]
    response_cache_service.set_json(PUBLIC_PRODUCTS_CACHE_KEY, items, PUBLIC_STORE_CACHE_TTL)
    return items


@router.get("/store/products/page", response_model=StoreProductPageResponse)
def products_page(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=80),
    popular: bool | None = Query(default=None),
    price_sort: str | None = Query(default=None, pattern="^(asc|desc)?$"),
    db: Session = Depends(get_db),
):
    # Endpoint público (sin login): limitado por IP para que nadie sin cuenta
    # pueda golpear en serie la búsqueda por descripción, la consulta más
    # pesada del catálogo (ver Fase 4 — rate_limit_service).
    rate_limit_service.check_rate_limit(
        "store_products_page",
        rate_limit_service.client_ip(request),
        max_requests=60,
        window_seconds=60,
        message="Demasiadas solicitudes al catálogo. Intenta de nuevo en un momento.",
    )
    items, total = store_service.list_products_page(
        db, page=page, page_size=page_size, search=search, category=category,
        popular=popular, price_sort=price_sort,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/store/products/{product_id}", response_model=StoreProductResponse)
def product_detail(product_id: int, db: Session = Depends(get_db)):
    return store_service.get_product(db, product_id)


@router.get("/store/payment-methods", response_model=list[StorePaymentMethodResponse])
def payment_methods(
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    cached = response_cache_service.get_json(PUBLIC_PAYMENT_METHODS_CACHE_KEY)
    if cached is not response_cache_service.CACHE_MISS:
        return cached
    items = [StorePaymentMethodResponse.model_validate(item).model_dump(mode="json") for item in store_service.list_payment_methods(db)]
    response_cache_service.set_json(PUBLIC_PAYMENT_METHODS_CACHE_KEY, items, PUBLIC_STORE_CACHE_TTL)
    return items


@router.post("/store/orders", response_model=StoreOrderResponse, status_code=201)
def create_order(
    background_tasks: BackgroundTasks,
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
    rate_limit_service.check_rate_limit(
        "create_order",
        str(current_user.id),
        max_requests=5,
        window_seconds=60,
        message="Demasiados pedidos en poco tiempo. Espera un momento.",
    )
    order = store_service.create_order(
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
    background_tasks.add_task(
        _dispatch_order_created_emails,
        order.customer_email,
        order.customer_first_name,
        order.reference,
        order.product_name,
        order.product_price,
        order.payment_type,
        order.status,
        order.id,
    )
    return order


@router.get("/store/orders/me", response_model=list[StoreOrderResponse])
def my_orders(
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    return store_service.list_user_orders(db, current_user.id)


@router.get("/store/orders/me/page", response_model=StoreOrderPageResponse)
def my_orders_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
):
    items, total = store_service.list_user_orders_page(db, current_user.id, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


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
    return Response(data, media_type=content_type, headers={"Cache-Control": CACHE_CONTROL_PRIVATE})


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
    return Response(data, media_type=content_type, headers={"Cache-Control": CACHE_CONTROL_IMMUTABLE})


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


@router.get("/admin/store/products/page", response_model=StoreProductAdminPageResponse)
def admin_products_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=160),
    popular: bool | None = Query(default=None),
    price_sort: str | None = Query(default=None, pattern="^(asc|desc)?$"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    items, total = store_service.list_products_page(
        db, page=page, page_size=page_size, include_inactive=True,
        search=search, popular=popular, price_sort=price_sort,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/admin/store/products", response_model=StoreProductAdminResponse, status_code=201)
def create_product(
    payload: StoreProductCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    product = store_service.create_product(db, payload, admin.id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return product


@router.put("/admin/store/products/{product_id}", response_model=StoreProductAdminResponse)
def update_product(
    product_id: int,
    payload: StoreProductUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    product = store_service.update_product(db, product_id, payload, admin.id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return product


@router.delete("/admin/store/products/{product_id}", response_model=StoreProductAdminResponse)
def archive_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    product = store_service.archive_product(db, product_id, admin.id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return product


@router.post("/admin/store/products/{product_id}/activate", response_model=StoreProductAdminResponse)
def activate_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    product = store_service.activate_product(db, product_id, admin.id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return product


@router.delete("/admin/store/products/{product_id}/permanent", status_code=204)
def delete_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    store_service.delete_product(db, product_id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
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
    media = store_service.add_product_media(
        db, product_id, file, sort_order, is_primary=is_primary
    )
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return media


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
    media = store_service.add_product_media_batch(
        db,
        product_id,
        files,
        primary_index=primary,
        start_sort_order=start_sort_order,
    )
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return media


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
    media = store_service.set_primary_media(db, product_id, media_id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
    return media


@router.delete("/admin/store/products/{product_id}/media/{media_id}", status_code=204)
def delete_media(
    product_id: int,
    media_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    store_service.delete_product_media(db, product_id, media_id)
    response_cache_service.invalidate(PUBLIC_PRODUCTS_CACHE_KEY)
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
    method = store_service.save_payment_method(db, payload, admin.id)
    response_cache_service.invalidate(PUBLIC_PAYMENT_METHODS_CACHE_KEY)
    return method


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
    method = store_service.save_payment_method(db, payload, admin.id, method_id)
    response_cache_service.invalidate(PUBLIC_PAYMENT_METHODS_CACHE_KEY)
    return method


@router.get("/admin/store/orders", response_model=list[StoreOrderResponse])
def admin_orders(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.list_all_orders(db)


@router.get("/admin/store/orders/page", response_model=StoreOrderPageResponse)
def admin_orders_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, max_length=30),
    status_group: str | None = Query(default=None, pattern="^(open|closed)$"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    items, total = store_service.list_all_orders_page(
        db, page=page, page_size=page_size, status=status, status_group=status_group,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


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
    return Response(data, media_type=content_type, headers={"Cache-Control": CACHE_CONTROL_PRIVATE})


@router.get("/admin/store/orders/{order_id}", response_model=StoreOrderResponse)
def admin_order_detail(
    order_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return store_service.get_order(db, order_id)


@router.patch("/admin/store/orders/{order_id}/status", response_model=StoreOrderResponse)
def update_status(
    order_id: int,
    payload: StoreOrderStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    previous_status = store_service.get_order(db, order_id).status
    order = store_service.update_order_status(db, order_id, payload)
    if order.status != previous_status:
        # admin_observations solo viaja como "motivo" al comprador en estados
        # de devolución/rechazo; en el resto es una nota interna del admin.
        background_tasks.add_task(
            _dispatch_order_status_changed_email,
            order.customer_email,
            order.customer_first_name,
            order.reference,
            order.product_name,
            order.status,
            order.admin_observations,
        )
    return order
