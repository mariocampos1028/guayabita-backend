import os
import json
import random
import string
from fastapi import HTTPException
from upstash_redis import Redis
from app.models import GameState, TurnState, Player
from app.game_logic import start_game as logic_start_game, _empty_turn
from dotenv import load_dotenv

load_dotenv()

ROOM_TTL = 60 * 60 * 24  # 24 horas en segundos
USER_ROOM_TTL = 60 * 60 * 24

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
    if len(room["players"]) >= 10:
        raise HTTPException(400, "La sala está llena (máx. 10 jugadores)")
    if any(p["user_id"] == user_id for p in room["players"]):
        # Ya está en la sala — devuelve el estado actual sin agregar de nuevo
        return room

    room["players"].append({"user_id": user_id, "username": username, "ready": True})
    redis.set(_room_key(code), json.dumps(room), ex=ROOM_TTL)
    redis.set(_user_room_key(user_id), code, ex=USER_ROOM_TTL)
    return room


def get_room(code: str) -> dict:
    raw = redis.get(_room_key(code))
    if not raw:
        raise HTTPException(404, "Sala no encontrada")
    return json.loads(raw)


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
