from datetime import datetime, timezone, date
from sqlalchemy import Integer, String, Float, DateTime, Text, ForeignKey, Boolean, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    id_document: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance: Mapped[float] = mapped_column(Float, default=5000.0, nullable=False)
    tournament_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Contadores del torneo en curso: se incrementan al cerrar cada partida y se
    # reinician al activar un torneo. Evitan recorrer game_history para rankear.
    tournament_games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tournament_games_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    referral_link_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Atribución de campaña de la visita que terminó en este registro (modelo
    # "último toque no orgánico" — ver utm.service.ts en el frontend). Se fija
    # una sola vez, al crear el usuario, y no vuelve a tocarse.
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(120), nullable=True)

    game_histories = relationship("GameHistory", back_populates="winner", foreign_keys="GameHistory.winner_id")
    referrals_made = relationship(
        "Referral",
        back_populates="referrer",
        foreign_keys="Referral.referrer_id",
    )


class GameHistory(Base):
    __tablename__ = "game_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    room_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    players_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON con resultado de cada jugador
    audit_log: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON compacto: historial completo
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    winner = relationship("User", back_populates="game_histories", foreign_keys=[winner_id])


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="Premio del torneo")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    winner_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    winner_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    winner_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    winner_prize_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    winner = relationship("User", foreign_keys=[winner_user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class RechargePackage(Base):
    __tablename__ = "recharge_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    guayabits: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    updated_by = relationship("User", foreign_keys=[updated_by_id])


class RechargePurchase(Base):
    __tablename__ = "recharge_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    package_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("recharge_packages.id"), nullable=True)
    package_name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    guayabits: Mapped[float] = mapped_column(Float, nullable=False)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    wompi_transaction_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    wompi_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    wompi_payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    package = relationship("RechargePackage", foreign_keys=[package_id])


class StoreGuayabitsRewardTier(Base):
    __tablename__ = "store_guayabits_reward_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    amount_from: Mapped[float] = mapped_column(Float, nullable=False)
    amount_to: Mapped[float] = mapped_column(Float, nullable=False)
    guayabits_reward: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class StoreProduct(Base):
    __tablename__ = "store_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    short_description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    guayabits_reward: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    allow_cash_on_delivery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_direct_payment: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    media = relationship(
        "StoreProductMedia",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="StoreProductMedia.is_primary.desc(), StoreProductMedia.sort_order",
    )
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    # `category` (arriba) es la categoría original, previa a soportar varias por
    # producto; se mantiene poblada con la primera categoría por compatibilidad,
    # pero ya no es la fuente de verdad para filtrar ni mostrar. Esa es
    # `category_links`, la relación N:M real.
    category_links = relationship(
        "StoreProductCategory",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    @property
    def categories(self) -> list[str]:
        """Categorías del producto, en el orden canónico de STORE_CATEGORIES."""
        from app.config.store_categories import STORE_CATEGORIES

        order = {name: i for i, name in enumerate(STORE_CATEGORIES)}
        names = {link.category for link in self.category_links}
        return sorted(names, key=lambda c: order.get(c, len(order)))


class StoreProductCategory(Base):
    """Relación N:M: un producto puede pertenecer a varias categorías."""
    __tablename__ = "store_product_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("store_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    product = relationship("StoreProduct", back_populates="category_links")


class StoreProductMedia(Base):
    __tablename__ = "store_product_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("store_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(700), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    product = relationship("StoreProduct", back_populates="media")


class StorePaymentMethod(Base):
    __tablename__ = "store_payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    method_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(160), nullable=False)
    identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    updated_by = relationship("User", foreign_keys=[updated_by_id])


class StoreOrder(Base):
    __tablename__ = "store_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("store_products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    product_price: Mapped[float] = mapped_column(Float, nullable=False)
    guayabits_reward: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    customer_first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    shipping_address: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_point: Mapped[str | None] = mapped_column(String(300), nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_method_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("store_payment_methods.id"), nullable=True
    )
    payment_method_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payment_receipt_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_receipt_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="en_proceso", index=True)
    admin_observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    guayabits_credited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Atribución de campaña vigente al momento de este pedido puntual (ver el
    # mismo campo en User — aquí se fija por cada compra, no solo una vez).
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    product = relationship("StoreProduct", foreign_keys=[product_id])
    payment_method = relationship("StorePaymentMethod", foreign_keys=[payment_method_id])


class BalanceMovement(Base):
    __tablename__ = "balance_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_balance: Mapped[float] = mapped_column(Float, nullable=False)
    new_balance: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id])


class BalanceAdjustmentLog(Base):
    __tablename__ = "balance_adjustment_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    previous_balance: Mapped[float] = mapped_column(Float, nullable=False)
    new_balance: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    admin = relationship("User", foreign_keys=[admin_id])


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    messages = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan", order_by="SupportMessage.created_at")


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lobby_inactivity_minutes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    verification_resend_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ReferralSettings(Base):
    __tablename__ = "referral_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    max_referrals_per_user: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    guayabits_per_referral: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    referrer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente", index=True)
    guayabits_rewarded: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[referrer_id])
    referred_user = relationship("User", foreign_keys=[referred_user_id])


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])


# ── Publicidad ────────────────────────────────────────────────────────────────

class AdvertisementBanner(Base):
    """Imagen promocional almacenada en Cloudflare R2."""
    __tablename__ = "advertisement_banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    public_url: Mapped[str] = mapped_column(String(700), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False, default="image/webp")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    advertisements = relationship("Advertisement", back_populates="banner")


class Advertisement(Base):
    """Regla de publicidad: qué banner mostrar, a quién y cuándo."""
    __tablename__ = "advertisements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    banner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("advertisement_banners.id"), nullable=False, index=True
    )
    balance_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="once_per_session")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    banner = relationship("AdvertisementBanner", back_populates="advertisements")
    created_by = relationship("User", foreign_keys=[created_by_id])
    sections = relationship(
        "AdvertisementSection",
        back_populates="advertisement",
        cascade="all, delete-orphan",
    )


class AdvertisementSection(Base):
    """Secciones donde aparece una publicidad (relación N:M via tabla de join)."""
    __tablename__ = "advertisement_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    advertisement_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("advertisements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    advertisement = relationship("Advertisement", back_populates="sections")
