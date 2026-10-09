"""Test setup: every test gets its own empty in-memory SQLite database and a moderator account."""
import os

# Must be set before the app is imported. Plain assignment so a developer's .env cannot leak in.
os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-signing"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["MODERATOR_USERNAME"] = ""
os.environ["MODERATOR_PASSWORD"] = ""
os.environ["BCRYPT_ROUNDS"] = "4"  # fast hashing in tests only

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.auth.service import create_or_update_moderator
from app.database import Base, get_db
from app.main import app

MODERATOR_USERNAME = "test-moderator"
MODERATOR_PASSWORD = "correct-horse-battery"
VALID_REPORT = {
    "category": "SECURITY",
    "description": "The admin panel is reachable without logging in.",
    "evidence_url": "https://example.com/proof",
}


@pytest.fixture()
def db_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(db_session_factory):
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with db_session_factory() as db:
        create_or_update_moderator(db, MODERATOR_USERNAME, MODERATOR_PASSWORD)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    response = client.post("/api/auth/login", json={"username": MODERATOR_USERNAME, "password": MODERATOR_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.fixture()
def create_report(client):
    def _create(**overrides):
        body = {**VALID_REPORT, **overrides}
        response = client.post("/api/reports", json=body)
        assert response.status_code == 201, response.text
        return response.json()["data"]["case_code"]

    return _create
