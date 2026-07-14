from typing import Literal, Optional
from pydantic import BaseModel, Field, EmailStr


TurnPhase = Literal["first-roll", "betting", "second-roll", "result"]
GameStatus = Literal["setup", "playing", "finished"]


# ── Juego ──────────────────────────────────────────────────────────────────────

class Player(BaseModel):
    id: int
    name: str
    balance: float


class TurnState(BaseModel):
    current_player_index: int
    phase: TurnPhase
    current_bet: float
    first_roll: Optional[int] = None
    second_roll: Optional[int] = None
    message: str


class GameState(BaseModel):
    players: list[Player]
    table_balance: float
    case_value: float
    turn: TurnState
    status: GameStatus
    winner: Optional[Player] = None


# ── Request bodies (juego) ─────────────────────────────────────────────────────

class PlayerConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    balance: float = Field(..., gt=0)


class StartGameRequest(BaseModel):
    players: list[PlayerConfig] = Field(..., min_length=2, max_length=10)
    case_value: float = Field(..., gt=0)


class PlaceBetRequest(BaseModel):
    amount: float = Field(..., gt=0)


# ── Auth ───────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    balance: float

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SessionResponse(BaseModel):
    user: UserResponse
    active_room: Optional[str] = None


# ── Salas ──────────────────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    case_value: float = Field(..., gt=0)


class RoomPlayer(BaseModel):
    user_id: int
    username: str
    ready: bool


class RoomResponse(BaseModel):
    code: str
    creator_id: int
    case_value: float
    status: str
    players: list[RoomPlayer]
    game_state: Optional[GameState] = None
