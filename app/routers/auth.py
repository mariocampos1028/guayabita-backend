from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.dependencies import get_current_user
from app.db.models_db import User
from app.models import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    SessionResponse,
    LeaderboardEntry,
    VerifyEmailRequest,
    MessageResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
    ChangePasswordRequest,
)
from app.services import auth_service
from app.services import room_service
from app.services.avatar_service import upload_user_avatar, delete_user_avatar, get_user_avatar_bytes
from app.emails import (
    send_password_changed_email,
    send_reset_password_email,
    send_verification_email,
    send_welcome_email,
)
from app.emails.settings import email_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _build_verify_url(token: str) -> str:
    return f"{email_settings.frontend_url}/verificar-correo?token={token}"


def _dispatch_welcome_email(
    email: str,
    username: str,
    balance: float,
    verify_token: str,
) -> None:
    send_welcome_email(
        to=email,
        username=username,
        balance=balance,
        verify_url=_build_verify_url(verify_token),
    )


def _build_reset_url(token: str) -> str:
    return f"{email_settings.frontend_url}/restablecer-contrasena?token={token}"


def _dispatch_reset_email(email: str, username: str, reset_token: str) -> None:
    send_reset_password_email(
        to=email,
        username=username,
        reset_url=_build_reset_url(reset_token),
    )


def _dispatch_password_changed_email(email: str, username: str) -> None:
    send_password_changed_email(to=email, username=username)


def _dispatch_verification_email(email: str, username: str, verify_token: str) -> None:
    send_verification_email(
        to=email,
        username=username,
        verify_url=_build_verify_url(verify_token),
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    auth_service.check_password_reset_rate_limit(str(req.email))
    user = auth_service.get_user_by_email(db, str(req.email))
    if user:
        reset_token = auth_service.create_password_reset_token(user.id)
        background_tasks.add_task(
            _dispatch_reset_email,
            user.email,
            user.username,
            reset_token,
        )
    return MessageResponse(message=auth_service.FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    req: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = auth_service.reset_password_with_token(db, req.token, req.new_password)
    background_tasks.add_task(
        _dispatch_password_changed_email,
        user.email,
        user.username,
    )
    return MessageResponse(message="Contraseña actualizada correctamente")


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    req: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = auth_service.register_user(
        db,
        req.username,
        req.email,
        req.password,
        first_name=req.first_name,
        last_name=req.last_name,
        phone=req.phone,
        address=req.address,
        birth_date=req.birth_date,
    )
    token = auth_service.create_token(user.id)
    auth_service.create_lobby_session(token, user.id)
    verify_token = auth_service.create_email_verification_token(user.id)
    background_tasks.add_task(
        _dispatch_welcome_email,
        user.email,
        user.username,
        user.balance,
        verify_token,
    )
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user, token = auth_service.login_user(db, req.username, req.password)
    auth_service.create_lobby_session(token, user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/verify-email", response_model=UserResponse)
def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = auth_service.verify_email_with_token(db, req.token)
    return UserResponse.model_validate(user)


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_token = auth_service.issue_verification_token_for_user(db, current_user.id)
    background_tasks.add_task(
        _dispatch_verification_email,
        current_user.email,
        current_user.username,
        verify_token,
    )
    return MessageResponse(message="Correo de verificación enviado")


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_user)):
    token = _extract_token(request)
    if token:
        auth_service.delete_lobby_session(token)
    return {"message": "Sesión cerrada"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.patch("/profile", response_model=UserResponse)
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = auth_service.update_user_profile(
        db,
        current_user.id,
        first_name=req.first_name,
        last_name=req.last_name,
        phone=req.phone,
        address=req.address,
    )
    return UserResponse.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(db, current_user.id, req.current_password, req.new_password)
    return MessageResponse(message="Contraseña actualizada correctamente")


@router.post("/avatar", response_model=UserResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sube o reemplaza la foto de perfil del usuario autenticado."""
    public_url = upload_user_avatar(current_user.id, file)
    user = auth_service.update_user_avatar_url(db, current_user.id, public_url)
    return UserResponse.model_validate(user)


@router.delete("/avatar", response_model=UserResponse)
def remove_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Elimina la foto de perfil en R2 y restaura el avatar por defecto."""
    delete_user_avatar(current_user.id)
    user = auth_service.reset_user_avatar_to_default(db, current_user.id)
    return UserResponse.model_validate(user)


@router.get("/avatar/{user_id}/image")
def get_avatar_image(user_id: int):
    """Proxy de imagen cuando R2_PUBLIC_URL no está configurada.

    También funciona como respaldo si el bucket no tiene acceso público.
    """
    data, content_type = get_user_avatar_bytes(user_id)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve, como máximo, los 50 jugadores con mayor saldo."""
    _ = current_user
    users = db.query(User).order_by(User.balance.desc(), User.id.asc()).limit(50).all()
    return [LeaderboardEntry.model_validate(user) for user in users]


@router.get("/session", response_model=SessionResponse)
def session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verifica sesión activa y renueva TTL. El frontend llama a esto
    al cargar la app y en el polling del lobby para mantener la sesión viva."""
    token = _extract_token(request)

    if token:
        still_active = auth_service.refresh_lobby_session(token)
        if not still_active:
            raise HTTPException(status_code=401, detail="Sesión expirada por inactividad")

    active_room = room_service.get_user_active_room(current_user.id)
    fresh_user = auth_service.get_user_by_id(db, current_user.id)
    return SessionResponse(
        user=UserResponse.model_validate(fresh_user),
        active_room=active_room,
    )
