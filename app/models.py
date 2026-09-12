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
    eliminated: bool = False


class TurnState(BaseModel):
    current_player_index: int
    phase: TurnPhase
    current_bet: float
    first_roll: Optional[int] = None
    second_roll: Optional[int] = None
    message: str
    deadline_at: Optional[datetime] = None


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


# ── Auditoría de partidas ──────────────────────────────────────────────────────

class GameHistorySummary(BaseModel):
    id: int
    room_code: str
    winner_id: int | None
    winner_username: str | None
    finished_at: datetime
    player_count: int
    has_audit: bool


class GameHistoryDetail(GameHistorySummary):
    players: list[dict]
    audit_log: list[dict]


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
    wait_expires_at: Optional[datetime] = None
    max_players: int = 10


class RoomSummary(BaseModel):
    code: str
    creator_username: str
    case_value: float
    player_count: int
    max_players: int = 10


# ── Paquetes de recarga ────────────────────────────────────────────────────────

PackageStatus = Literal["active", "inactive"]


class RechargePackageBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price: float = Field(..., gt=0)
    guayabits: float = Field(..., gt=0)
    status: PackageStatus = "active"
    popular: bool = False


class RechargePackageCreateRequest(RechargePackageBase):
    pass


class RechargePackageUpdateRequest(RechargePackageBase):
    pass


class RechargePackageResponse(RechargePackageBase):
    id: int
    created_at: datetime
    updated_at: datetime
    updated_by_id: int | None = None
    updated_by_username: str | None = None

    model_config = {"from_attributes": True}


class RechargePackagePublicResponse(BaseModel):
    id: int
    name: str
    price: float
    guayabits: float
    popular: bool

    model_config = {"from_attributes": True}


# ── Pagos Wompi ────────────────────────────────────────────────────────────────

PurchaseStatus = Literal["pending", "approved", "cancelled", "declined", "error", "voided"]


class CheckoutRequest(BaseModel):
    package_id: int = Field(..., gt=0)


class CheckoutResponse(BaseModel):
    purchase_id: int
    reference: str
    public_key: str
    currency: str
    amount_in_cents: int
    signature: str
    redirect_url: str | None = None
    customer_email: str
    customer_full_name: str


class PurchaseResponse(BaseModel):
    id: int
    package_name: str
    price: float
    guayabits: float
    reference: str
    status: PurchaseStatus
    wompi_transaction_id: str | None = None
    wompi_status: str | None = None
    wompi_payment_method: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Tienda y pedidos ──────────────────────────────────────────────────────────

StoreProductStatus = Literal["active", "inactive"]
StoreOrderStatus = Literal[
    "en_validacion",
    "en_proceso",
    "en_alistamiento",
    "en_reparto",
    "entregado",
    "rechazado",
    "devuelto_correccion",
]
StorePaymentType = Literal["contraentrega", "directo"]
StorePaymentMethodType = Literal["bre_b", "nequi", "daviplata"]


class StoreProductMediaResponse(BaseModel):
    id: int
    media_type: Literal["image", "video"]
    url: str
    sort_order: int
    is_primary: bool = False

    model_config = {"from_attributes": True}


class StoreGuayabitsRewardTierRequest(BaseModel):
    amount_from: float = Field(..., ge=0)
    amount_to: float = Field(..., gt=0)
    guayabits_reward: float = Field(..., ge=0)


class StoreGuayabitsRewardTierResponse(StoreGuayabitsRewardTierRequest):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GuayabitsRewardCalculationResponse(BaseModel):
    price: float
    guayabits_reward: float


class StoreProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    category: str = Field(..., min_length=2, max_length=80)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        from app.config.store_categories import STORE_CATEGORIES

        normalized = value.strip()
        if normalized not in STORE_CATEGORIES:
            raise ValueError(
                "Categoría inválida. Usa una de: "
                + ", ".join(STORE_CATEGORIES)
            )
        return normalized
    short_description: str = Field(..., min_length=2, max_length=300)
    description: str = Field(..., min_length=2, max_length=5000)
    price: float = Field(..., gt=0)
    guayabits_reward: float = Field(..., ge=0)
    is_popular: bool = False
    allow_cash_on_delivery: bool = True
    allow_direct_payment: bool = True
    status: StoreProductStatus = "active"

    @field_validator("allow_direct_payment")
    @classmethod
    def validate_payment_option(cls, value: bool, info):
        if not value and info.data.get("allow_cash_on_delivery") is False:
            raise ValueError("El producto debe permitir al menos una forma de pago")
        return value


class StoreProductAdminFields(BaseModel):
    product_code: str = Field(default="", max_length=80)


class StoreProductCreateRequest(StoreProductBase, StoreProductAdminFields):
    pass


class StoreProductUpdateRequest(StoreProductBase, StoreProductAdminFields):
    pass


class StoreProductResponse(StoreProductBase):
    id: int
    media: list[StoreProductMediaResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoreProductAdminResponse(StoreProductResponse):
    product_code: str = ""

    model_config = {"from_attributes": True}


class StorePaymentMethodBase(BaseModel):
    method_type: StorePaymentMethodType
    display_name: str = Field(..., min_length=2, max_length=80)
    owner_name: str = Field(..., min_length=2, max_length=160)
    identifier: str = Field(..., min_length=3, max_length=160)
    instructions: str = Field(default="", max_length=1000)
    is_active: bool = True


class StorePaymentMethodRequest(StorePaymentMethodBase):
    pass


class StorePaymentMethodResponse(StorePaymentMethodBase):
    id: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoreOrderResponse(BaseModel):
    id: int
    reference: str
    product_id: int | None
    product_name: str
    product_price: float
    guayabits_reward: float
    quantity: int
    customer_first_name: str
    customer_last_name: str
    customer_email: str
    customer_phone: str
    shipping_address: str
    department: str
    city: str
    reference_point: str | None
    customer_notes: str | None
    payment_type: StorePaymentType
    payment_method_id: int | None
    payment_method_name: str | None
    payment_receipt_url: str | None
    status: StoreOrderStatus
    admin_observations: str | None
    guayabits_credited: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoreOrderShippingUpdateRequest(BaseModel):
    shipping_address: str = Field(..., min_length=5, max_length=255)
    department: str = Field(..., min_length=2, max_length=80)
    city: str = Field(..., min_length=2, max_length=100)
    reference_point: str | None = Field(default=None, max_length=300)
    customer_notes: str | None = Field(default=None, max_length=1000)


class AdminBalanceAdjustmentRequest(BaseModel):
    new_balance: float = Field(..., ge=0)
    justification: str = Field(..., min_length=5, max_length=500)


class BalanceAdjustmentLogResponse(BaseModel):
    id: int
    user_id: int
    admin_id: int
    previous_balance: float
    new_balance: float
    delta: float
    justification: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BalanceAdjustmentLogDetailResponse(BalanceAdjustmentLogResponse):
    user_username: str
    user_full_name: str
    admin_username: str


class StoreOrderAuditEventResponse(BaseModel):
    id: int
    reference: str
    customer_name: str
    product_name: str
    status: str
    payment_type: str
    updated_at: datetime


class AdminBalanceAdjustmentResponse(BaseModel):
    user: UserResponse
    log: BalanceAdjustmentLogResponse


class StoreOrderStatusUpdateRequest(BaseModel):
    status: StoreOrderStatus
    admin_observations: str | None = Field(default=None, max_length=2000)


# ── Soporte ───────────────────────────────────────────────────────────────────
SupportCategory = Literal["solicitud", "peticion", "felicitacion", "sugerencia"]
SupportTicketStatus = Literal["open", "closed"]


class SupportTicketCreateRequest(BaseModel):
    category: SupportCategory
    title: str = Field(..., min_length=3, max_length=160)
    detail: str = Field(..., min_length=3, max_length=5000)


class SupportMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class SupportMessageResponse(BaseModel):
    id: int
    sender_id: int
    sender_role: Literal["user", "admin"]
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class SupportTicketResponse(BaseModel):
    id: int
    user_id: int
    username: str
    customer_first_name: str
    customer_last_name: str
    customer_email: str
    customer_phone: str
    category: SupportCategory
    title: str
    status: SupportTicketStatus
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    messages: list[SupportMessageResponse] = Field(default_factory=list)
