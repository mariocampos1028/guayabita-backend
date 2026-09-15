from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models_db import User
from app.services.auth_service import decode_token, get_user_by_id, check_lobby_session

bearer_scheme = HTTPBearer()

EMAIL_NOT_VERIFIED_DETAIL = "Debes verificar tu correo electrónico antes de continuar"

LOBBY_SESSION_EXEMPT_PATHS = {
    "/auth/session",
    "/auth/session-config",
    "/auth/logout",
    "/auth/login",
    "/auth/register",
    "/auth/verify-email",
    "/auth/forgot-password",
    "/auth/reset-password",
    "/auth/check-username",
}


def ensure_email_verified(user: User) -> None:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMAIL_NOT_VERIFIED_DETAIL,
        )


def get_current_user_jwt_only(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Valida solo el JWT, sin comprobar la sesión de inactividad en Redis."""
    user_id = decode_token(credentials.credentials)
    return get_user_by_id(db, user_id)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: JWT válido y sesión de lobby activa en Redis."""
    user = get_current_user_jwt_only(credentials, db)
    path = request.url.path.rstrip("/") or "/"
    if path in LOBBY_SESSION_EXEMPT_PATHS or path.startswith("/payments/wompi"):
        return user
    if not check_lobby_session(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada por inactividad",
        )
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: se requiere cuenta de administrador",
        )
    return current_user


def get_current_non_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los administradores no pueden usar la tienda como clientes",
        )
    return current_user


def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    ensure_email_verified(current_user)
    return current_user


def get_current_verified_non_admin(
    current_user: User = Depends(get_current_verified_user),
) -> User:
    if current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los administradores no pueden usar la tienda como clientes",
        )
    return current_user
