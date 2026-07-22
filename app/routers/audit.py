from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_admin
from app.models import GameHistoryDetail, GameHistorySummary
from app.services import game_history_service

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


@router.get("", response_model=list[GameHistorySummary])
def list_audit_records(
    room_code: str | None = Query(default=None, max_length=10),
    date: date | None = Query(default=None, description="Fecha de finalización (YYYY-MM-DD)"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    histories = game_history_service.list_histories(
        db,
        room_code=room_code,
        on_date=date,
    )
    return [_to_summary(h) for h in histories]


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
