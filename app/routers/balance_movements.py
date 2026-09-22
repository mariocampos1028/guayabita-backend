from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_non_admin
from app.models import BalanceMovementPageResponse, BalanceMovementResponse
from app.services import balance_movement_service

router = APIRouter(tags=["balance-movements"])


@router.get("/balance-movements", response_model=BalanceMovementPageResponse)
def list_my_balance_movements(
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    movements, total = balance_movement_service.list_user_movements_page(
        db, current_user.id, page=page, page_size=page_size,
    )
    return {
        "items": [BalanceMovementResponse.model_validate(item) for item in movements],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
