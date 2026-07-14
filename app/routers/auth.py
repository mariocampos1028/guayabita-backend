from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.dependencies import get_current_user
from app.db.models_db import User
from app.models import RegisterRequest, LoginRequest, TokenResponse, UserResponse, SessionResponse
from app.services import auth_service
from app.services import room_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_user(db, req.username, req.email, req.password)
    token = auth_service.create_token(user.id)
    # Crea sesión en Redis con TTL 5 min
    auth_service.create_lobby_session(token, user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user, token = auth_service.login_user(db, req.username, req.password)
    # Crea sesión en Redis con TTL 5 min
    auth_service.create_lobby_session(token, user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_user)):
    token = _extract_token(request)
    if token:
        auth_service.delete_lobby_session(token)
    return {"message": "Sesión cerrada"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.get("/session", response_model=SessionResponse)
def session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verifica sesión activa y renueva TTL. El frontend llama a esto
    al cargar la app y en el polling del lobby para mantener la sesión viva."""
    token = _extract_token(request)

    # Si el token existe, renueva la sesión de lobby
    if token:
        still_active = auth_service.refresh_lobby_session(token)
        if not still_active:
            # Sesión expiró por inactividad en el lobby
            raise HTTPException(status_code=401, detail="Sesión expirada por inactividad")

    active_room = room_service.get_user_active_room(current_user.id)
    fresh_user = auth_service.get_user_by_id(db, current_user.id)
    return SessionResponse(
        user=UserResponse.model_validate(fresh_user),
        active_room=active_room,
    )
