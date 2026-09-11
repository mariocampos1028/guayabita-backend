from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin
from app.models import (
    AdminBalanceAdjustmentRequest,
    AdminBalanceAdjustmentResponse,
    BalanceAdjustmentLogDetailResponse,
    UserResponse,
)
from app.services import admin_users_service

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/search", response_model=list[UserResponse])
def search_users(
    q: str = Query(..., min_length=2, max_length=120),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return admin_users_service.search_users(db, q)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return admin_users_service.get_user_by_id(db, user_id)


@router.post("/{user_id}/balance", response_model=AdminBalanceAdjustmentResponse)
def adjust_balance(
    user_id: int,
    payload: AdminBalanceAdjustmentRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user, log = admin_users_service.adjust_user_balance(
        db,
        user_id=user_id,
        admin_id=admin.id,
        new_balance=payload.new_balance,
        justification=payload.justification,
    )
    return AdminBalanceAdjustmentResponse(
        user=UserResponse.model_validate(user),
        log=BalanceAdjustmentLogResponse.model_validate(log),
    )


@router.get("/{user_id}/balance-logs", response_model=list[BalanceAdjustmentLogDetailResponse])
def user_balance_logs(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    admin_users_service.get_user_by_id(db, user_id)
    return admin_users_service.list_balance_logs(db, user_id=user_id)
