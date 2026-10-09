"""Application settings, read from environment variables (and an optional .env file)."""
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # real environment variables take priority over .env

# Values that are fine for a local demo but must never be used in production.
WEAK_PASSWORDS = {"change-me-please", "moderator-demo-pass", "password", "admin"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    secret_key: str
    access_token_minutes: int
    cors_origins: list[str]
    moderator_username: str | None
    moderator_password: str | None
    bcrypt_rounds: int
    jwt_algorithm: str = "HS256"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


@lru_cache
def get_settings() -> Settings:
    app_env = (os.getenv("APP_ENV") or "development").strip().lower()
    if app_env not in {"development", "production"}:
        raise RuntimeError("APP_ENV must be 'development' or 'production'.")

    secret_key = _clean(os.getenv("SECRET_KEY"))
    moderator_password = _clean(os.getenv("MODERATOR_PASSWORD"))

    if app_env == "production":
        if not secret_key or len(secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be set to a random value of 32+ characters in production.")
        if moderator_password and (len(moderator_password) < 10 or moderator_password in WEAK_PASSWORDS):
            raise RuntimeError("MODERATOR_PASSWORD is too weak for production (10+ characters, not a default).")
    elif not secret_key:
        # Development only: random key, so tokens stop working when the server restarts.
        secret_key = secrets.token_urlsafe(48)

    origins = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "").split(",") if o.strip()]

    return Settings(
        app_env=app_env,
        database_url=_clean(os.getenv("DATABASE_URL")) or "sqlite:///./whistledrop.db",
        secret_key=secret_key,
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES") or 60),
        cors_origins=origins,
        moderator_username=_clean(os.getenv("MODERATOR_USERNAME")),
        moderator_password=moderator_password,
        bcrypt_rounds=int(os.getenv("BCRYPT_ROUNDS") or 12),
    )
