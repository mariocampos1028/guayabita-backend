import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models_db import User, GameHistory
from app.dependencies import get_current_user
from app.models import GameState, PlaceBetRequest
from app.services import room_service, auth_service
from app.services import game_audit_service
import app.game_logic as logic

router = APIRouter(prefix="/game", tags=["game"])


def _get_state_or_404(code: str) -> GameState:
    return room_service.get_game_state(code.upper())


def _validate_turn(code: str, current_user: User, state: GameState) -> None:
    """Lanza 403 si el usuario autenticado no es el jugador en turno."""
    room = room_service.get_room(code.upper())
    player_ids: list[int] = room.get("player_user_ids", [])
    current_index = state.turn.current_player_index
    if current_index >= len(player_ids):
        raise HTTPException(403, "No se puede determinar el jugador en turno")
    expected_user_id = player_ids[current_index]
    if current_user.id != expected_user_id:
        # Devuelve el nombre del jugador en turno para que el frontend lo muestre
        current_player_name = state.players[current_index].name if current_index < len(state.players) else "otro jugador"
        raise HTTPException(403, f"No es tu turno. Esperando a {current_player_name}")


def _player_context(code: str) -> tuple[list[int], list[str]]:
    room = room_service.get_room(code)
    user_ids: list[int] = room.get("player_user_ids", [])
    usernames = [p["username"] for p in room.get("players", [])]
    return user_ids, usernames


def _current_player_meta(code: str, state: GameState) -> tuple[int | None, str]:
    user_ids, usernames = _player_context(code)
    idx = state.turn.current_player_index
    user_id = user_ids[idx] if idx < len(user_ids) else None
    username = usernames[idx] if idx < len(usernames) else state.players[idx].name
    return user_id, username


def _save_and_return(code: str, state: GameState, db: Session) -> GameState:
    state = logic.apply_turn_timeout(state)
    room_service.save_game_state(code, state)
    if state.status == "finished":
        _persist_result(code, state, db)
    return state


def _load_state_with_timeout(code: str) -> GameState:
    state = _get_state_or_404(code)
    updated = logic.apply_turn_timeout(state)
    if updated.model_dump() != state.model_dump():
        room_service.save_game_state(code, updated)
    return updated


def _persist_result(code: str, state: GameState, db: Session) -> None:
    try:
        room = room_service.get_room(code)
    except HTTPException:
        # La sala ya fue eliminada de Redis — _persist_result ya corrió antes
        return

    player_ids: list[int] = room.get("player_user_ids", [])

    winner_db_id = None
    players_result = []

    for i, player in enumerate(state.players):
        user_id = player_ids[i] if i < len(player_ids) else None
        if user_id:
            original_balance = room["players"][i].get("original_balance", player.balance)
            delta = player.balance - original_balance
            if delta != 0:
                auth_service.update_user_balance(db, user_id, delta)

        if state.winner and state.winner.id == player.id:
            winner_db_id = player_ids[i] if i < len(player_ids) else None

        players_result.append({
            "player_index": i,
            "user_id": user_id,
            "name": player.name,
            "final_balance": player.balance,
        })

    history = GameHistory(
        room_code=code,
        winner_id=winner_db_id,
        players_json=json.dumps(players_result, separators=(",", ":")),
        audit_log=json.dumps(
            room.get("audit_log", []),
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )
    db.add(history)
    db.commit()

    # Limpia Redis: borra user_room de cada jugador (para que /auth/session
    # no los devuelva a esta sala) pero deja room:{code} vivo 5 minutos más
    # con un TTL corto para que los jugadores que estén en polling puedan
    # leer el estado "finished" y mostrar el overlay de fin de juego.
    for uid in player_ids:
        if uid:
            room_service.leave_finished_room(uid)
    room_service.expire_room(code, ttl_seconds=300)  # 5 minutos


@router.get("/{code}/state", response_model=GameState)
def get_state(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    code = code.upper()
    state = _load_state_with_timeout(code)
    if state.status == "finished":
        _persist_result(code, state, db)
    return state


@router.post("/{code}/roll", response_model=GameState)
def roll_dice(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = code.upper()
    state = _load_state_with_timeout(code)
    _validate_turn(code, current_user, state)
    user_id, username = _current_player_meta(code, state)
    new_state = logic.roll_dice(state)
    room_service.append_audit_log(
        code,
        game_audit_service.build_roll(state, new_state, user_id, username),
    )
    if new_state.status == "finished":
        user_ids, usernames = _player_context(code)
        room_service.append_audit_log(
            code,
            game_audit_service.build_game_end(new_state, user_ids, usernames),
        )
    return _save_and_return(code, new_state, db)


@router.post("/{code}/bet", response_model=GameState)
def place_bet(
    code: str,
    req: PlaceBetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = code.upper()
    state = _load_state_with_timeout(code)
    _validate_turn(code, current_user, state)
    new_state = logic.place_bet(state, req.amount)
    user_id, username = _current_player_meta(code, new_state)
    room_service.append_audit_log(
        code,
        game_audit_service.build_bet(new_state, user_id, username),
    )
    return _save_and_return(code, new_state, db)


@router.post("/{code}/next-turn", response_model=GameState)
def next_turn(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = code.upper()
    state = _load_state_with_timeout(code)
    _validate_turn(code, current_user, state)
    new_state = logic.next_turn(state)
    user_id, username = _current_player_meta(code, new_state)
    room_service.append_audit_log(
        code,
        game_audit_service.build_next_turn(state, new_state, user_id, username),
    )
    return _save_and_return(code, new_state, db)
