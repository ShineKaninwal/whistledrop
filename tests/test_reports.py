"""Reporter-facing behaviour: anonymous submission, case codes, public lookup, validation, privacy."""
import pytest

from app.services import report_service
from app.utils.case_code import ALPHABET, generate_case_code, is_valid_case_code
from tests.conftest import VALID_REPORT


def test_create_report_anonymously(client):
    response = client.post("/api/reports", json=VALID_REPORT)  # no auth header, no identity
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert is_valid_case_code(body["data"]["case_code"])
    assert body["data"]["status"] == "SUBMITTED"


def test_case_codes_are_random_unique_and_well_formed():
    codes = {generate_case_code() for _ in range(2000)}
    assert len(codes) == 2000
    assert all(is_valid_case_code(c) and c.startswith("WD-") and len(c) == 11 for c in codes)
    assert all(ch in ALPHABET for c in codes for ch in c[3:])


def test_case_code_collision_is_retried(client, monkeypatch, create_report):
    first = create_report()
    codes = iter([first, first, "WD-ABCDEFGH"])  # two collisions, then a fresh code
    monkeypatch.setattr(report_service, "generate_case_code", lambda: next(codes))
    assert create_report() == "WD-ABCDEFGH"


def test_public_lookup_by_case_code(client, create_report):
    code = create_report()
    response = client.get(f"/api/reports/{code}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_code"] == code
    assert data["status"] == "SUBMITTED"
    assert data["update"]  # a default message exists even before a moderator writes one


def test_lookup_accepts_lowercase_and_spaces(client, create_report):
    code = create_report()
    assert client.get(f"/api/reports/{code.lower()}").status_code == 200


def test_unknown_case_code_returns_404(client):
    response = client.get("/api/reports/WD-ZZZZZZZZ")
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "error": {"code": "report_not_found", "message": "No report found for this case code.", "details": None},
    }


@pytest.mark.parametrize("bad_code", ["1", "WD-123", "WD-0OIL1111", "XX-7K4P9X2M", "WD-7K4P9X2MM"])
def test_malformed_case_code_returns_422(client, bad_code):
    response = client.get(f"/api/reports/{bad_code}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_case_code"


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "A long enough description here."},  # category missing
        {"category": "SECURITY"},  # description missing
        {"category": "NOPE", "description": "A long enough description here."},  # bad category
        {"category": "SECURITY", "description": "short"},  # too short
        {"category": "SECURITY", "description": "x" * 5001},  # too long
        {"category": "SECURITY", "description": "A long enough description here.", "evidence_url": "not a url"},
        {"category": "SECURITY", "description": "A long enough description here.", "evidence_url": "javascript:alert(1)"},
        {"category": "SECURITY", "description": "A long enough description here.", "email": "me@example.com"},  # identity field
    ],
)
def test_invalid_report_data_is_rejected(client, payload):
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]


def test_malformed_json_returns_400(client):
    response = client.post("/api/reports", content='{"category": ', headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "malformed_json"


def test_validation_errors_do_not_echo_submitted_text(client):
    secret = "my-very-private-sentence-that-must-not-come-back"
    response = client.post("/api/reports", json={"category": "NOPE", "description": secret})
    assert secret not in response.text


def test_public_responses_expose_only_allowed_fields(client, create_report):
    created = client.post("/api/reports", json=VALID_REPORT).json()["data"]
    assert set(created) == {"case_code", "status", "message", "created_at"}

    lookup = client.get(f"/api/reports/{created['case_code']}").json()["data"]
    assert set(lookup) == {"case_code", "status", "update", "created_at", "updated_at"}

    # Nothing private or internal leaks anywhere in the public payloads.
    combined = (str(created) + str(lookup)).lower()
    for forbidden in ("id", "description", "evidence", "category", "token", "password"):
        assert forbidden not in set(created) | set(lookup)
    assert VALID_REPORT["description"].lower() not in combined
    assert "example.com" not in combined
