"""FastAPI dependency that protects moderator routes."""
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database import get_db
from app.models import Moderator
from app.utils.errors import AppError

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the `access_token` returned by `POST /api/auth/login`.",
)


def _unauthorized(message: str) -> AppError:
    return AppError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def get_current_moderator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Moderator:
    if credentials is None:
        raise _unauthorized("Authentication required.")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired token.")
    moderator = db.scalar(select(Moderator).where(Moderator.username == payload["sub"]))
    if moderator is None:
        raise _unauthorized("Invalid or expired token.")
    return moderator
