"""Creating moderator accounts (there is no public sign-up)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import Moderator


def create_or_update_moderator(db: Session, username: str, password: str) -> tuple[Moderator, bool]:
    """Returns (moderator, created). An existing account gets its password replaced."""
    moderator = db.scalar(select(Moderator).where(Moderator.username == username))
    created = moderator is None
    if created:
        moderator = Moderator(username=username, password_hash=hash_password(password))
        db.add(moderator)
    else:
        moderator.password_hash = hash_password(password)
    db.commit()
    return moderator, created


def ensure_moderator(db: Session, username: str, password: str) -> bool:
    """Startup helper: create the account from environment variables only if it is missing."""
    if db.scalar(select(Moderator).where(Moderator.username == username)):
        return False
    create_or_update_moderator(db, username, password)
    return True
