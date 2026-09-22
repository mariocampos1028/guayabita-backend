from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin
from app.models import (
    BalanceAdjustmentLogPageResponse,
    GameHistoryDetail,
    GameHistoryPageResponse,
    GameHistorySummary,
    StoreOrderAuditEventPageResponse,
    StoreOrderAuditEventResponse,
)
from app.services import admin_users_service, game_history_service, store_service

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


def _to_summary(history) -> GameHistorySummary:
    players = game_history_service.parse_players_json(history.players_json)
    winner_name = history.winner.username if history.winner else None
    return GameHistorySummary(
        id=history.id,
        room_code=history.room_code,
        winner_id=history.winner_id,
        winner_username=winner_name,
        finished_at=history.finished_at,
        player_count=len(players),
        has_audit=bool(history.audit_log),
    )


@router.get("", response_model=GameHistoryPageResponse)
def list_audit_records(
    room_code: str | None = Query(default=None, max_length=10),
    date: date | None = Query(default=None, description="Fecha de finalización (YYYY-MM-DD)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    histories, total = game_history_service.list_histories_page(
        db,
        room_code=room_code,
        on_date=date,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_to_summary(h) for h in histories],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/system/balance", response_model=BalanceAdjustmentLogPageResponse)
def list_balance_audit(
    user_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    items, total = admin_users_service.list_balance_logs_page(
        db, user_id=user_id, q=q, page=page, page_size=page_size,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/events/orders", response_model=StoreOrderAuditEventPageResponse)
def list_store_order_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    orders, total = store_service.list_all_orders_page(db, page=page, page_size=page_size)
    items = [
        StoreOrderAuditEventResponse(
            id=order.id,
            reference=order.reference,
            customer_name=f"{order.customer_first_name} {order.customer_last_name}".strip(),
            product_name=order.product_name,
            status=order.status,
            payment_type=order.payment_type,
            updated_at=order.updated_at,
        )
        for order in orders
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/{history_id}", response_model=GameHistoryDetail)
def get_audit_record(
    history_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    history = game_history_service.get_history_detail(db, history_id)
    summary = _to_summary(history)
    return GameHistoryDetail(
        **summary.model_dump(),
        players=game_history_service.parse_players_json(history.players_json),
        audit_log=game_history_service.parse_audit_log(history.audit_log),
    )
