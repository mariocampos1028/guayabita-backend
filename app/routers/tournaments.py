from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies import get_current_admin, get_current_user
from app.db.models_db import User
from app.models import TournamentResponse, TournamentUpdateRequest, TournamentContributeRequest, TournamentBalanceResponse
from app.services import tournament_service

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def _to_response(tournament) -> TournamentResponse:
    return TournamentResponse.model_validate(tournament)


@router.get("", response_model=list[TournamentResponse])
def list_tournaments(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    return [_to_response(t) for t in tournament_service.list_all_tournaments(db)]


@router.post("/draft", response_model=TournamentResponse)
def create_tournament_draft(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    tournament = tournament_service.create_new_draft(db, admin.id)
    return _to_response(tournament)


@router.get("/current", response_model=TournamentResponse | None)
def get_current_tournament(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    tournament = tournament_service.get_display_tournament(db)
    if not tournament:
        return None
    return _to_response(tournament)


@router.post("/contribute", response_model=TournamentBalanceResponse)
def contribute_to_tournament(
    req: TournamentContributeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = tournament_service.contribute_to_tournament(db, current_user.id, req.amount)
    return TournamentBalanceResponse(balance=user.balance, tournament_balance=user.tournament_balance)


@router.get("/current/edit", response_model=TournamentResponse)
def get_tournament_for_edit(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    tournament = tournament_service.get_or_create_editable_tournament(db, admin.id)
    return _to_response(tournament)


@router.put("/current", response_model=TournamentResponse)
def save_current_tournament(
    req: TournamentUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    tournament = tournament_service.save_tournament(
        db,
        admin.id,
        tournament_id=req.tournament_id,
        title=req.title,
        description=req.description,
        ends_at=req.ends_at,
        is_active=req.is_active,
    )
    return _to_response(tournament)


@router.post("/current/image", response_model=TournamentResponse)
def upload_tournament_image(
    file: UploadFile = File(...),
    tournament_id: int | None = Query(default=None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    tournament = tournament_service.get_tournament_for_save(db, tournament_id, admin.id)
    tournament_service.upload_tournament_image(db, tournament.id, file)
    db.refresh(tournament)
    return _to_response(tournament)


@router.get("/{tournament_id}", response_model=TournamentResponse)
def get_tournament_by_id(
    tournament_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _ = admin
    tournament = tournament_service.get_tournament_by_id(db, tournament_id)
    return _to_response(tournament)


@router.get("/{tournament_id}/image")
def get_tournament_image(tournament_id: int):
    """Proxy de imagen del premio cuando R2_PUBLIC_URL no está configurada."""
    data, content_type = tournament_service.get_tournament_image_bytes(tournament_id)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
