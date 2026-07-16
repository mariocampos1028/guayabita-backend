from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models_db import User
from app.dependencies import get_current_user
from app.models import CreateRoomRequest, RoomResponse, RoomSummary, GameState
from app.services import room_service, auth_service

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _format_room(room: dict) -> RoomResponse:
    game_state = None
    if room.get("game_state"):
        import json
        game_state = GameState.model_validate(room["game_state"])
    return RoomResponse(
        code=room["code"],
        creator_id=room["creator_id"],
        case_value=room["case_value"],
        status=room["status"],
        players=room["players"],
        game_state=game_state,
    )


@router.post("/create", response_model=RoomResponse, status_code=201)
def create_room(
    req: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
):
    min_balance = req.case_value * 2
    if current_user.balance < min_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente. Para un case de ${req.case_value:.0f} necesitás al menos ${min_balance:.0f} (tu saldo: ${current_user.balance:.0f})",
        )
    room = room_service.create_room(current_user.id, current_user.username, req.case_value)
    return _format_room(room)


@router.post("/join/{code}", response_model=RoomResponse)
def join_room(
    code: str,
    current_user: User = Depends(get_current_user),
):
    room = room_service.get_room(code.upper())
    case_value = room["case_value"]
    min_balance = case_value * 2
    if current_user.balance < min_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente. Para un case de ${case_value:.0f} necesitás al menos ${min_balance:.0f} (tu saldo: ${current_user.balance:.0f})",
        )
    room = room_service.join_room(code.upper(), current_user.id, current_user.username)
    return _format_room(room)


@router.get("/open", response_model=list[RoomSummary])
def list_open_rooms(current_user: User = Depends(get_current_user)):
    """Salas en espera disponibles para unirse sin conocer el código."""
    rooms = room_service.list_waiting_rooms(current_user.id)
    return [RoomSummary.model_validate(room) for room in rooms]


@router.get("/{code}", response_model=RoomResponse)
def get_room(
    code: str,
    current_user: User = Depends(get_current_user),
):
    room = room_service.get_room(code.upper())
    return _format_room(room)


@router.post("/{code}/start", response_model=RoomResponse)
def start_room(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = code.upper()
    room = room_service.get_room(code)

    # Obtiene el saldo actualizado de cada jugador desde PostgreSQL
    balances: dict[int, float] = {}
    for p in room["players"]:
        user = auth_service.get_user_by_id(db, p["user_id"])
        balances[p["user_id"]] = user.balance

    room_service.start_room(code, current_user.id, balances)
    updated_room = room_service.get_room(code)
    return _format_room(updated_room)


@router.delete("/{code}", status_code=204)
def cancel_room(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Solo el creador puede cancelar la sala. Elimina la sala y
    desvincula a todos los jugadores de ella en Redis."""
    room_service.cancel_room(code.upper(), current_user.id)


@router.post("/{code}/leave", status_code=204)
def leave_room(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Un jugador (no creador) abandona la sala."""
    room_service.leave_room(code.upper(), current_user.id)
