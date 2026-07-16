import os
import secrets
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.db.models_db import User
from app.emails.settings import email_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "changeme")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "5000"))
LOBBY_SESSION_TTL = 60 * 3  # 3 minutos de inactividad en el lobby

EMAIL_VERIFY_PREFIX = "email_verify:"
PASSWORD_RESET_PREFIX = "password_reset:"
PASSWORD_RESET_RATE_PREFIX = "pwd_reset_rate:"
PASSWORD_RESET_RATE_MAX = 3
PASSWORD_RESET_RATE_WINDOW = 15 * 60  # 15 minutos

FORGOT_PASSWORD_MESSAGE = (
    "Si el correo está registrado, enviamos instrucciones para restablecer tu contraseña."
)


def _get_redis():
    """Importación lazy para evitar circular imports."""
    from app.services.room_service import redis
    return redis


def _session_key(token: str) -> str:
    return f"session:{token}"


# ── Passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────────

def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    """Decodifica el token y devuelve el user_id. Lanza 401 si es inválido."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")


# ── Sesión en Redis (solo lobby) ───────────────────────────────────────────────

def create_lobby_session(token: str, user_id: int) -> None:
    """Crea la llave de sesión en Redis al hacer login. TTL: 5 min."""
    _get_redis().set(_session_key(token), str(user_id), ex=LOBBY_SESSION_TTL)


def refresh_lobby_session(token: str) -> bool:
    """Renueva el TTL de la sesión. Devuelve False si ya expiró."""
    redis = _get_redis()
    key = _session_key(token)
    exists = redis.get(key)
    if exists is None:
        return False
    redis.expire(key, LOBBY_SESSION_TTL)
    return True


def delete_lobby_session(token: str) -> None:
    """Elimina la sesión de Redis al hacer logout."""
    _get_redis().delete(_session_key(token))


def check_lobby_session(token: str) -> bool:
    """Verifica si la sesión de lobby sigue activa."""
    return _get_redis().get(_session_key(token)) is not None


# ── Usuarios ───────────────────────────────────────────────────────────────────

def register_user(db: Session, username: str, email: str, password: str) -> User:
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        balance=INITIAL_BALANCE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, username: str, password: str) -> tuple[User, str]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_token(user.id)
    return user, token


def get_user_by_id(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def update_user_balance(db: Session, user_id: int, delta: float) -> User:
    """Aplica un delta al saldo del usuario y persiste en PostgreSQL."""
    user = get_user_by_id(db, user_id)
    user.balance += delta
    db.commit()
    db.refresh(user)
    return user


# ── Verificación de correo ─────────────────────────────────────────────────────

def _email_verify_key(token: str) -> str:
    return f"{EMAIL_VERIFY_PREFIX}{token}"


def create_email_verification_token(user_id: int) -> str:
    """Genera un token de un solo uso y lo guarda en Redis."""
    token = secrets.token_urlsafe(32)
    ttl_seconds = email_settings.verify_token_ttl_hours * 3600
    _get_redis().set(_email_verify_key(token), str(user_id), ex=ttl_seconds)
    return token


def verify_email_with_token(db: Session, token: str) -> User:
    """Valida el token, marca el correo como verificado y lo invalida."""
    redis = _get_redis()
    key = _email_verify_key(token)
    user_id_str = redis.get(key)
    if user_id_str is None:
        raise HTTPException(status_code=400, detail="Enlace inválido o expirado")

    user = get_user_by_id(db, int(user_id_str))
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

    redis.delete(key)
    return user


def issue_verification_token_for_user(db: Session, user_id: int) -> str:
    """Devuelve un token nuevo para reenviar verificación."""
    user = get_user_by_id(db, user_id)
    if user.email_verified:
        raise HTTPException(status_code=400, detail="El correo ya está verificado")
    return create_email_verification_token(user.id)


# ── Restablecimiento de contraseña ─────────────────────────────────────────────

def _password_reset_key(token: str) -> str:
    return f"{PASSWORD_RESET_PREFIX}{token}"


def _password_reset_rate_key(email: str) -> str:
    return f"{PASSWORD_RESET_RATE_PREFIX}{email.strip().lower()}"


def check_password_reset_rate_limit(email: str) -> None:
    """Limita solicitudes de reset por correo para evitar abuso."""
    redis = _get_redis()
    key = _password_reset_rate_key(email)
    count = redis.get(key)
    if count is not None and int(count) >= PASSWORD_RESET_RATE_MAX:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Espera unos minutos e inténtalo de nuevo.",
        )
    new_count = int(count) + 1 if count is not None else 1
    redis.set(key, str(new_count), ex=PASSWORD_RESET_RATE_WINDOW)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_password_reset_token(user_id: int) -> str:
    """Genera un token de un solo uso para restablecer contraseña."""
    token = secrets.token_urlsafe(32)
    ttl_seconds = email_settings.password_reset_token_ttl_minutes * 60
    _get_redis().set(_password_reset_key(token), str(user_id), ex=ttl_seconds)
    return token


def reset_password_with_token(db: Session, token: str, new_password: str) -> User:
    """Valida el token, actualiza la contraseña y lo invalida."""
    redis = _get_redis()
    key = _password_reset_key(token)
    user_id_str = redis.get(key)
    if user_id_str is None:
        raise HTTPException(status_code=400, detail="Enlace inválido o expirado")

    user = get_user_by_id(db, int(user_id_str))
    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    redis.delete(key)
    return user
