import json
import os
import random
import string
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import HTTPException
from upstash_redis import Redis
from app.models import GameState, TurnState, Player
from app.game_logic import start_game as logic_start_game, _empty_turn
from app.services import game_audit_service

load_dotenv()

ROOM_TTL = 60 * 60 * 24  # 24 horas en segundos
USER_ROOM_TTL = 60 * 60 * 24
WAIT_TIMEOUT_SECONDS = 300
MAX_PLAYERS = 10

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL", ""),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN", ""),
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _room_key(code: str) -> str:
    return f"room:{code}"

def _user_room_key(user_id: int) -> str:
    return f"user_room:{user_id}"

def _generate_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _serialize(state: GameState) -> str:
    return state.model_dump_json()

def _deserialize(data: str) -> GameState:
    return GameState.model_validate_json(data)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sync_wait_timer(room: dict) -> None:
    if room.get("status") != "waiting":
        room.pop("wait_expires_at", None)
        return
    if len(room.get("players", [])) > 1:
        if not room.get("wait_expires_at"):
            room["wait_expires_at"] = (_now() + timedelta(seconds=WAIT_TIMEOUT_SECONDS)).isoformat()
    else:
        room.pop("wait_expires_at", None)


def _expire_waiting_room_if_needed(code: str, room: dict) -> None:
    if room.get("status") != "waiting":
        return
    expires_raw = room.get("wait_expires_at")
    if not expires_raw:
        return
    expires = datetime.fromisoformat(expires_raw)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires > _now():
        return
    for player in room.get("players", []):
        redis.delete(_user_room_key(player["user_id"]))
    redis.delete(_room_key(code))
    raise HTTPException(
        status_code=410,
        detail="La sala expiró: se superaron los 5 minutos de espera sin iniciar la partida.",
    )


# ── Sala ───────────────────────────────────────────────────────────────────────

def create_room(creator_id: int, creator_username: str, case_value: float) -> dict:
    """Crea una sala vacía en Redis. El creador queda como primer jugador."""
    code = _generate_code()
    # Asegura que el código sea único
    while redis.get(_room_key(code)):
        code = _generate_code()

    room_data = {
        "code": code,
        "creator_id": creator_id,
        "case_value": case_value,
        "status": "waiting",  # waiting | playing | finished
        "players": [
            {"user_id": creator_id, "username": creator_username, "ready": True}
        ],
        "game_state": None,
    }
    redis.set(_room_key(code), json.dumps(room_data), ex=ROOM_TTL)
    # Asocia el usuario a esta sala
    redis.set(_user_room_key(creator_id), code, ex=USER_ROOM_TTL)
    return room_data


def join_room(code: str, user_id: int, username: str) -> dict:
    """Un usuario se une a una sala existente."""
    raw = redis.get(_room_key(code))
    if not raw:
        raise HTTPException(404, "Sala no encontrada o expirada")

    room = json.loads(raw)
    if room["status"] != "waiting":
        raise HTTPException(400, "La partida ya comenzó o terminó")
    if len(room["players"]) >= MAX_PLAYERS:
        raise HTTPException(400, "La sala está llena (máximo 10 jugadores)")
    if any(p["user_id"] == user_id for p in room["players"]):
        # Ya está en la sala — devuelve el estado actual sin agregar de nuevo
        return room

    room["players"].append({"user_id": user_id, "username": username, "ready": True})
    _sync_wait_timer(room)
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)
    redis.set(_user_room_key(user_id), code, ex=USER_ROOM_TTL)
    return room


def get_room(code: str) -> dict:
    raw = redis.get(_room_key(code))
    if not raw:
        raise HTTPException(404, "Sala no encontrada")
    room = json.loads(raw)
    _expire_waiting_room_if_needed(code, room)
    return room


def start_room(code: str, user_id: int, balances: dict[int, float]) -> GameState:
    """
    Inicia la partida de una sala.
    balances: {user_id: balance_actual} consultado de PostgreSQL.
    """
    room = get_room(code)
    if room["creator_id"] != user_id:
        raise HTTPException(403, "Solo el creador puede iniciar la partida")
    if room["status"] != "waiting":
        raise HTTPException(400, "La partida ya fue iniciada")
    if len(room["players"]) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 jugadores")

    from app.models import PlayerConfig as PC, StartGameRequest

    players_config = [
        PC(name=p["username"], balance=balances.get(p["user_id"], 5000))
        for p in room["players"]
    ]
    req = StartGameRequest(players=players_config, case_value=room["case_value"])
    state = logic_start_game(req)

    room["status"] = "playing"
    room["game_state"] = json.loads(_serialize(state))
    # Mapea player index → user_id para poder actualizar saldos luego
    room["player_user_ids"] = [p["user_id"] for p in room["players"]]
    # Guarda el saldo original de cada jugador (antes de descontar el case inicial)
    # para poder calcular el delta correcto al terminar la partida
    for i, p in enumerate(room["players"]):
        p["original_balance"] = balances.get(p["user_id"], 5000)
    room["audit_log"] = [
        game_audit_service.build_game_start(
            case_value=room["case_value"],
            state=state,
            players_meta=room["players"],
            user_ids=room["player_user_ids"],
        )
    ]
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)
    return state


def get_game_state(code: str) -> GameState:
    room = get_room(code)
    if not room.get("game_state"):
        raise HTTPException(400, "La partida no ha comenzado")
    return _deserialize(json.dumps(room["game_state"]))


def save_game_state(code: str, state: GameState) -> None:
    room = get_room(code)
    room["game_state"] = json.loads(_serialize(state))
    if state.status == "finished":
        room["status"] = "finished"
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)


def append_audit_log(code: str, entry: dict) -> None:
    """Agrega una entrada al log de auditoría de la partida (almacenado en Redis)."""
    room = get_room(code)
    log: list = room.setdefault("audit_log", [])
    entry = dict(entry)
    entry["seq"] = len(log) + 1
    log.append(entry)
    room["audit_log"] = log
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)


def get_user_active_room(user_id: int) -> str | None:
    """Devuelve el código de sala activa del usuario o None."""
    code = redis.get(_user_room_key(user_id))
    if not code:
        return None
    # Verifica que la sala todavía exista y no haya terminado
    raw = redis.get(_room_key(code))
    if not raw:
        redis.delete(_user_room_key(user_id))
        return None
    room = json.loads(raw)
    if room["status"] == "finished":
        redis.delete(_user_room_key(user_id))
        return None
    return code


def leave_finished_room(user_id: int) -> None:
    redis.delete(_user_room_key(user_id))


def cancel_room(code: str, user_id: int) -> None:
    """El creador cancela la sala: desvincula a todos los jugadores y borra la sala."""
    room = get_room(code)
    if room["creator_id"] != user_id:
        raise HTTPException(403, "Solo el creador puede cancelar la sala")
    if room["status"] != "waiting":
        raise HTTPException(400, "No se puede cancelar una sala que ya inició")

    # Desvincula a todos los jugadores
    for p in room["players"]:
        redis.delete(_user_room_key(p["user_id"]))

    # Borra la sala
    redis.delete(_room_key(code))


def leave_room(code: str, user_id: int) -> None:
    """Un jugador abandona la sala (no el creador)."""
    room = get_room(code)
    if room["status"] != "waiting":
        raise HTTPException(400, "No se puede abandonar una sala que ya inició")
    if room["creator_id"] == user_id:
        raise HTTPException(400, "El creador no puede abandonar la sala, solo cancelarla")
    if not any(p["user_id"] == user_id for p in room["players"]):
        raise HTTPException(404, "No estás en esta sala")

    # Quita al jugador de la lista
    room["players"] = [p for p in room["players"] if p["user_id"] != user_id]
    _sync_wait_timer(room)
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)

    # Desvincula al jugador de la sala
    redis.delete(_user_room_key(user_id))


def delete_room(code: str) -> None:
    """Elimina la llave de la sala en Redis inmediatamente."""
    redis.delete(_room_key(code))


def expire_room(code: str, ttl_seconds: int) -> None:
    """Reduce el TTL de la sala para que expire pronto.
    Se usa al terminar la partida: basta con que los jugadores puedan
    leer el estado 'finished' durante unos minutos más."""
    redis.expire(_room_key(code), ttl_seconds)


def get_player_user_id(code: str, player_index: int) -> int | None:
    """Retorna el user_id del jugador en la posición player_index."""
    room = get_room(code)
    ids = room.get("player_user_ids", [])
    if player_index < len(ids):
        return ids[player_index]
    return None


def list_waiting_rooms(current_user_id: int) -> list[dict]:
    """Lista salas en espera a las que el usuario aún no pertenece."""
    open_rooms: list[dict] = []
    try:
        keys = redis.keys("room:*")
    except Exception:
        return []

    if not keys:
        return []

    for key in keys:
        code = key.split(":", 1)[-1]
        raw = redis.get(_room_key(code))
        if not raw:
            continue

        room = json.loads(raw)
        if room.get("status") != "waiting":
            continue
        if len(room["players"]) >= MAX_PLAYERS:
            continue
        if any(p["user_id"] == current_user_id for p in room["players"]):
            continue

        creator_username = "Desconocido"
        for player in room["players"]:
            if player["user_id"] == room["creator_id"]:
                creator_username = player["username"]
                break

        open_rooms.append(
            {
                "code": room["code"],
                "creator_username": creator_username,
                "case_value": room["case_value"],
                "player_count": len(room["players"]),
                "max_players": MAX_PLAYERS,
            }
        )

    open_rooms.sort(key=lambda item: (-item["player_count"], item["code"]))
    return open_rooms
