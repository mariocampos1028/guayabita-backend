import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.db.models_db import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "changeme")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "5000"))
LOBBY_SESSION_TTL = 60 * 1  # 2 minutos de inactividad en el lobby


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
