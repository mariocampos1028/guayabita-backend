"""Consulta de historial de partidas para auditoría."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.models_db import GameHistory


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def list_histories(
    db: Session,
    *,
    room_code: str | None = None,
    on_date: date | None = None,
    limit: int = 100,
) -> list[GameHistory]:
    query = (
        db.query(GameHistory)
        .options(joinedload(GameHistory.winner))
        .order_by(GameHistory.finished_at.desc())
    )

    if room_code:
        code = room_code.strip().upper()
        if code:
            query = query.filter(GameHistory.room_code.ilike(f"%{code}%"))

    if on_date:
        start, end = _day_bounds(on_date)
        query = query.filter(GameHistory.finished_at >= start, GameHistory.finished_at <= end)

    return query.limit(min(limit, 200)).all()


def get_history_detail(db: Session, history_id: int) -> GameHistory:
    history = (
        db.query(GameHistory)
        .options(joinedload(GameHistory.winner))
        .filter(GameHistory.id == history_id)
        .first()
    )
    if not history:
        raise HTTPException(status_code=404, detail="Registro de partida no encontrado")
    return history


def parse_players_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def parse_audit_log(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
