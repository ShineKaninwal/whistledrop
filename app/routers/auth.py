from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, dummy_hash, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import Moderator
from app.schemas.auth import LoginRequest, TokenOut
from app.schemas.common import ApiResponse, ErrorResponse
from app.utils.errors import AppError
from app.utils.responses import ok

router = APIRouter(prefix="/api/auth", tags=["Moderator authentication"])


@router.post(
    "/login",
    response_model=ApiResponse[TokenOut],
    summary="Moderator login",
    description=(
        "Exchange moderator credentials for a JWT. In Swagger, click **Authorize** (top right) "
        "and paste the returned `access_token` to call the protected moderator endpoints."
    ),
    responses={401: {"model": ErrorResponse, "description": "Wrong username or password."}},
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    moderator = db.scalar(select(Moderator).where(Moderator.username == payload.username.strip()))
    # Always run one bcrypt check so unknown users and wrong passwords look the same.
    password_ok = verify_password(payload.password, moderator.password_hash if moderator else dummy_hash())
    if moderator is None or not password_ok:
        raise AppError(
            401,
            "invalid_credentials",
            "Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(moderator.username)
    expires_in = get_settings().access_token_minutes * 60
    return ok(TokenOut(access_token=token, expires_in=expires_in))
