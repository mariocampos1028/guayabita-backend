"""Lógica de negocio para torneos de premios."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.models_db import Tournament, User
from app.services.image_processing import (
    OUTPUT_CONTENT_TYPE,
    process_prize_webp,
    read_upload_bytes,
    validate_upload,
)
from app.services.r2_storage_service import (
    get_r2_storage_service,
    tournament_object_key,
    tournament_public_url,
)

logger = logging.getLogger(__name__)

MIN_LEAD_MINUTES = 3
DEFAULT_PRIZE_IMAGE = "/images/ps5-prize-640.png"
DEFAULT_TITLE = "PlayStation 5"
DEFAULT_DESCRIPTION = "El jugador que alcance el primer lugar podrá ganar una PlayStation 5."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_active_tournament(db: Session) -> Tournament | None:
    return (
        db.query(Tournament)
        .filter(Tournament.status == "active")
        .order_by(Tournament.id.desc())
        .first()
    )


def get_latest_finished_tournament(db: Session) -> Tournament | None:
    return (
        db.query(Tournament)
        .filter(Tournament.status == "finished")
        .order_by(Tournament.finished_at.desc(), Tournament.id.desc())
        .first()
    )


def get_leaderboard_winner(db: Session) -> User | None:
    return db.query(User).order_by(User.balance.desc(), User.id.asc()).first()


def finalize_tournament(db: Session, tournament: Tournament) -> Tournament:
    winner = get_leaderboard_winner(db)
    tournament.status = "finished"
    tournament.is_active = False
    tournament.finished_at = _now()
    tournament.updated_at = _now()

    if winner:
        tournament.winner_user_id = winner.id
        tournament.winner_username = winner.username
        tournament.winner_avatar_url = winner.avatar_url
        tournament.winner_balance = winner.balance
        tournament.winner_prize_title = tournament.title

    db.commit()
    db.refresh(tournament)
    return tournament


def maybe_finalize_tournament(db: Session, tournament: Tournament) -> Tournament:
    if tournament.status != "active" or not tournament.ends_at:
        return tournament

    if _ensure_aware(tournament.ends_at) <= _now():
        return finalize_tournament(db, tournament)
    return tournament


def get_other_active_tournament(db: Session, exclude_id: int) -> Tournament | None:
    return (
        db.query(Tournament)
        .filter(Tournament.status == "active", Tournament.id != exclude_id)
        .first()
    )


def get_or_create_editable_tournament(db: Session, admin_id: int) -> Tournament:
    active = get_active_tournament(db)
    if active:
        active = maybe_finalize_tournament(db, active)
        if active.status == "active":
            return active

    draft = (
        db.query(Tournament)
        .filter(Tournament.status == "draft")
        .order_by(Tournament.id.desc())
        .first()
    )
    if draft:
        return draft

    finished = get_latest_finished_tournament(db)
    tournament = Tournament(
        title=finished.title if finished else DEFAULT_TITLE,
        description=finished.description if finished else DEFAULT_DESCRIPTION,
        image_url=(finished.image_url if finished else None) or DEFAULT_PRIZE_IMAGE,
        status="draft",
        is_active=False,
        created_by_id=admin_id,
    )
    db.add(tournament)
    db.commit()
    db.refresh(tournament)
    return tournament


def get_tournament_for_save(
    db: Session,
    tournament_id: int | None,
    admin_id: int,
) -> Tournament:
    if tournament_id is not None:
        tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
        if not tournament:
            raise HTTPException(status_code=404, detail="Torneo no encontrado")
        if tournament.status == "finished":
            raise HTTPException(status_code=400, detail="No se puede editar un torneo finalizado")
        return tournament
    return get_or_create_editable_tournament(db, admin_id)


def get_display_tournament(db: Session) -> Tournament | None:
    active = get_active_tournament(db)
    if active:
        active = maybe_finalize_tournament(db, active)
        if active.status == "active":
            return active

    return get_latest_finished_tournament(db)


def validate_ends_at_activation(ends_at: datetime) -> datetime:
    ends_at = _ensure_aware(ends_at)
    minimum = _now() + timedelta(minutes=MIN_LEAD_MINUTES)
    if ends_at < minimum:
        raise HTTPException(
            status_code=400,
            detail="La fecha de finalización debe ser al menos 3 minutos en el futuro",
        )
    return ends_at


def validate_ends_at_update(ends_at: datetime, current: Tournament) -> datetime:
    ends_at = _ensure_aware(ends_at)
    if ends_at <= _now():
        raise HTTPException(status_code=400, detail="La fecha de finalización debe ser en el futuro")

    if current.status == "active" and current.ends_at:
        previous = _ensure_aware(current.ends_at)
        if ends_at >= previous:
            return ends_at

    return validate_ends_at_activation(ends_at)


def save_tournament(
    db: Session,
    admin_id: int,
    *,
    tournament_id: int | None,
    title: str,
    description: str,
    ends_at: datetime | None,
    is_active: bool,
) -> Tournament:
    current = get_tournament_for_save(db, tournament_id, admin_id)

    if current.status == "finished":
        raise HTTPException(status_code=400, detail="No se puede editar un torneo finalizado")

    current.title = title.strip() or DEFAULT_TITLE
    current.description = description.strip()
    current.updated_at = _now()

    if not ends_at:
        if is_active or current.status == "active":
            raise HTTPException(status_code=400, detail="Debes indicar la fecha de finalización")
    else:
        if current.status == "active":
            current.ends_at = validate_ends_at_update(ends_at, current)
        elif is_active:
            current.ends_at = validate_ends_at_activation(ends_at)
        else:
            current.ends_at = _ensure_aware(ends_at)

    if is_active:
        other = get_other_active_tournament(db, current.id)
        if other:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'Ya hay un torneo activo ("{other.title}"). '
                    "Edítalo o espera a que finalice antes de activar otro."
                ),
            )

        if current.status != "active":
            current.status = "active"
            current.is_active = True
            current.started_at = _now()
            current.finished_at = None
            current.winner_user_id = None
            current.winner_username = None
            current.winner_avatar_url = None
            current.winner_balance = None
            current.winner_prize_title = None
        else:
            current.is_active = True
            current.status = "active"
    else:
        if current.status == "active":
            raise HTTPException(
                status_code=400,
                detail="No puedes desactivar un torneo en curso. Solo puedes modificar la fecha de finalización.",
            )
        current.is_active = False
        current.status = "draft"

    db.commit()
    db.refresh(current)
    return current


def upload_tournament_image(db: Session, tournament_id: int, file: UploadFile) -> str:
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Torneo no encontrado")
    if tournament.status == "finished":
        raise HTTPException(status_code=400, detail="No se puede editar un torneo finalizado")

    raw = read_upload_bytes(file)
    validate_upload(file, raw)
    webp_bytes = process_prize_webp(raw)

    storage = get_r2_storage_service()
    key = tournament_object_key(tournament_id)

    try:
        if storage.object_exists(key):
            storage.delete_object(key)
        storage.upload_object(key, webp_bytes, OUTPUT_CONTENT_TYPE)
    except Exception as exc:
        logger.exception("Error al subir imagen de torneo %s", tournament_id)
        raise HTTPException(status_code=500, detail="Error al subir la imagen") from exc

    public_url = tournament_public_url(tournament_id)
    tournament.image_url = public_url
    tournament.updated_at = _now()
    db.commit()
    db.refresh(tournament)
    return public_url


def get_tournament_image_bytes(tournament_id: int) -> tuple[bytes, str]:
    storage = get_r2_storage_service()
    key = tournament_object_key(tournament_id)
    try:
        if not storage.object_exists(key):
            raise HTTPException(status_code=404, detail="Imagen no encontrada")
        return storage.get_object_bytes(key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error al leer imagen de torneo %s", tournament_id)
        raise HTTPException(status_code=500, detail="Error al obtener la imagen") from exc
