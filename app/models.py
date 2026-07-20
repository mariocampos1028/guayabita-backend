from typing import Literal, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field, EmailStr, field_validator


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
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    phone: str = Field(..., min_length=7, max_length=30)
    address: str = Field(..., min_length=5, max_length=255)
    birth_date: date

    @field_validator("birth_date")
    @classmethod
    def must_be_adult(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise ValueError("Debes ser mayor de 18 años para registrarte")
        return value


class UpdateProfileRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    phone: str = Field(..., min_length=7, max_length=30)
    address: str = Field(..., min_length=5, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    balance: float
    tournament_balance: float
    email_verified: bool
    first_name: str
    last_name: str
    phone: str
    address: str
    birth_date: date | None
    avatar_url: str | None
    is_admin: bool
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=6, max_length=100)


class LeaderboardEntry(BaseModel):
    id: int
    username: str
    tournament_balance: float

    model_config = {"from_attributes": True}


class TournamentContributeRequest(BaseModel):
    amount: float = Field(..., gt=0)


class TournamentBalanceResponse(BaseModel):
    balance: float
    tournament_balance: float


# ── Torneos ────────────────────────────────────────────────────────────────────

TournamentStatus = Literal["draft", "active", "finished"]


class TournamentResponse(BaseModel):
    id: int
    title: str
    description: str
    image_url: str | None
    status: TournamentStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime
    ends_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    winner_user_id: int | None
    winner_username: str | None
    winner_avatar_url: str | None
    winner_balance: float | None
    winner_prize_title: str | None

    model_config = {"from_attributes": True}


class TournamentUpdateRequest(BaseModel):
    tournament_id: int | None = None
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2000)
    ends_at: datetime | None = None
    is_active: bool


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


class RoomSummary(BaseModel):
    code: str
    creator_username: str
    case_value: float
    player_count: int
    max_players: int = 10
