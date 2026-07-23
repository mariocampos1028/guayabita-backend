from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_user
from app.models import CheckoutRequest, CheckoutResponse, PurchaseResponse
from app.services import payment_service, wompi_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = payment_service.create_checkout(db, current_user, payload.package_id)
    return CheckoutResponse(**data)


@router.post("/{purchase_id}/cancel", response_model=PurchaseResponse)
def cancel_checkout(
    purchase_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    purchase = payment_service.cancel_purchase(db, purchase_id, current_user.id)
    return PurchaseResponse.model_validate(purchase)


@router.get("/history", response_model=list[PurchaseResponse])
def purchase_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    purchases = payment_service.list_user_purchases(db, current_user.id)
    return [PurchaseResponse.model_validate(p) for p in purchases]


@router.get("/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(
    purchase_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    purchase = payment_service.get_purchase_for_user(db, purchase_id, current_user.id)
    return PurchaseResponse.model_validate(purchase)


@router.get("/wompi/return")
def wompi_return(request: Request):
    """Redirección del navegador tras PSE u otros métodos que salen del widget."""
    transaction_id = request.query_params.get("id")
    return RedirectResponse(
        url=wompi_service.frontend_result_url(transaction_id),
        status_code=302,
    )


@router.get("/wompi/webhook")
def wompi_browser_return(request: Request):
    """PSE a veces redirige aquí si en Wompi se configuró mal la URL de retorno."""
    transaction_id = request.query_params.get("id")
    return RedirectResponse(
        url=wompi_service.frontend_result_url(transaction_id),
        status_code=302,
    )


@router.post("/wompi/webhook")
async def wompi_webhook(request: Request, db: Session = Depends(get_db)):
    event = await request.json()
    payment_service.handle_wompi_event(db, event)
    return {"status": "ok"}
