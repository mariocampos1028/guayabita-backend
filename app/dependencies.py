from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models_db import User
from app.services.auth_service import decode_token, get_user_by_id

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extrae y valida el JWT, devuelve el usuario autenticado."""
    user_id = decode_token(credentials.credentials)
    return get_user_by_id(db, user_id)
