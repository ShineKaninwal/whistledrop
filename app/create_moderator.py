"""Create or reset a moderator account:  python -m app.create_moderator --username alice"""
import argparse
import getpass
import sys

from app.auth.service import create_or_update_moderator
from app.database import Base, SessionLocal, engine
import app.models  # noqa: F401  (registers tables)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or reset a WhistleDrop moderator.")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        print("Passwords must match and be at least 8 characters.", file=sys.stderr)
        return 1

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _, created = create_or_update_moderator(db, args.username.strip(), password)
    print(f"Moderator '{args.username}' {'created' if created else 'password updated'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
