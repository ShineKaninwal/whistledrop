"""Moderator login and route protection."""
import pytest

from tests.conftest import MODERATOR_PASSWORD, MODERATOR_USERNAME

PROTECTED = [
    ("GET", "/api/moderator/reports"),
    ("GET", "/api/moderator/stats"),
    ("GET", "/api/moderator/reports/WD-ABCDEFGH"),
    ("PATCH", "/api/moderator/reports/WD-ABCDEFGH/status"),
]


def test_moderator_login_returns_token(client):
    response = client.post("/api/auth/login", json={"username": MODERATOR_USERNAME, "password": MODERATOR_PASSWORD})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["expires_in"] > 0


@pytest.mark.parametrize(
    "credentials",
    [
        {"username": MODERATOR_USERNAME, "password": "wrong-password"},
        {"username": "nobody", "password": MODERATOR_PASSWORD},
    ],
)
def test_login_with_bad_credentials_returns_401(client, credentials):
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.parametrize("method,path", PROTECTED)
def test_moderator_routes_reject_missing_token(client, method, path):
    response = client.request(method, path, json={"status": "UNDER_REVIEW"} if method == "PATCH" else None)
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.parametrize("method,path", PROTECTED)
def test_moderator_routes_reject_invalid_token(client, method, path):
    headers = {"Authorization": "Bearer not.a.real-token"}
    response = client.request(method, path, headers=headers, json={"status": "UNDER_REVIEW"} if method == "PATCH" else None)
    assert response.status_code == 401
