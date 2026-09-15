from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_non_admin
from app.models import BalanceMovementResponse
from app.services import balance_movement_service

router = APIRouter(tags=["balance-movements"])


@router.get("/balance-movements", response_model=list[BalanceMovementResponse])
def list_my_balance_movements(
    current_user: User = Depends(get_current_non_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=500),
):
    movements = balance_movement_service.list_user_movements(
        db,
        current_user.id,
        limit=limit,
    )
    return [BalanceMovementResponse.model_validate(item) for item in movements]
