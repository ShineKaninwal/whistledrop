"""Moderator behaviour: listing, filters, pagination, status workflow, stats."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import ReportStatus
from app.services import workflow


def patch_status(client, headers, code, status, message=None):
    return client.patch(f"/api/moderator/reports/{code}/status", headers=headers, json={"status": status, "message": message})


def test_moderator_lists_reports(client, auth_headers, create_report):
    code = create_report()
    response = client.get("/api/moderator/reports", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["case_code"] == code
    assert "id" not in item  # internal database ID is never exposed


def test_moderator_views_report_detail(client, auth_headers, create_report):
    code = create_report()
    data = client.get(f"/api/moderator/reports/{code}", headers=auth_headers).json()["data"]
    assert data["description"].startswith("The admin panel")
    assert data["evidence_url"] == "https://example.com/proof"
    assert data["allowed_transitions"] == ["UNDER_REVIEW"]
    assert "id" not in data


def test_status_update_is_visible_to_reporter(client, auth_headers, create_report):
    code = create_report()
    response = patch_status(client, auth_headers, code, "UNDER_REVIEW", "We have started looking into this.")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNDER_REVIEW"

    public = client.get(f"/api/reports/{code}").json()["data"]
    assert public["status"] == "UNDER_REVIEW"
    assert public["update"] == "We have started looking into this."
    assert public["updated_at"] >= public["created_at"]


def test_full_lifecycle_ends_in_final_status(client, auth_headers, create_report):
    code = create_report()
    assert patch_status(client, auth_headers, code, "UNDER_REVIEW").status_code == 200
    assert patch_status(client, auth_headers, code, "RESOLVED", "Fixed.").status_code == 200
    final = patch_status(client, auth_headers, code, "DISMISSED")
    assert final.status_code == 409  # RESOLVED is final


@pytest.mark.parametrize("target", ["RESOLVED", "DISMISSED"])
def test_cannot_skip_review(client, auth_headers, create_report, target):
    code = create_report()
    response = patch_status(client, auth_headers, code, target)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"
    assert client.get(f"/api/reports/{code}").json()["data"]["status"] == "SUBMITTED"


def test_invalid_status_value_and_long_message_rejected(client, auth_headers, create_report):
    code = create_report()
    assert patch_status(client, auth_headers, code, "DONE").status_code == 422
    assert patch_status(client, auth_headers, code, "UNDER_REVIEW", "x" * 501).status_code == 422


def test_same_status_requires_message_and_edits_only_the_message(client, auth_headers, create_report):
    code = create_report()
    patch_status(client, auth_headers, code, "UNDER_REVIEW")
    assert patch_status(client, auth_headers, code, "UNDER_REVIEW").status_code == 422
    edited = patch_status(client, auth_headers, code, "UNDER_REVIEW", "Waiting for more information.")
    assert edited.status_code == 200
    assert client.get(f"/api/reports/{code}").json()["data"]["update"] == "Waiting for more information."


def test_update_unknown_report_returns_404(client, auth_headers):
    assert patch_status(client, auth_headers, "WD-ZZZZZZZZ", "UNDER_REVIEW").status_code == 404


def test_filter_by_category_status_search_and_date(client, auth_headers, create_report):
    security = create_report(category="SECURITY", description="Open admin panel on the portal.")
    create_report(category="HARASSMENT", description="Hostile messages in a group chat.")
    patch_status(client, auth_headers, security, "UNDER_REVIEW")

    def codes(**params):
        response = client.get("/api/moderator/reports", headers=auth_headers, params=params)
        assert response.status_code == 200
        return [item["case_code"] for item in response.json()["data"]["items"]]

    assert codes(category="SECURITY") == [security]
    assert codes(status="UNDER_REVIEW") == [security]
    assert len(codes(status="SUBMITTED")) == 1
    assert codes(q="admin") == [security]
    assert codes(q=security.lower()) == [security]
    assert codes(category="SECURITY", status="SUBMITTED") == []

    today = datetime.now(timezone.utc).date()
    assert len(codes(created_from=today.isoformat(), created_to=today.isoformat())) == 2
    assert codes(created_from=(today + timedelta(days=1)).isoformat()) == []


def test_invalid_filters_are_rejected(client, auth_headers):
    assert client.get("/api/moderator/reports", headers=auth_headers, params={"category": "NOPE"}).status_code == 422
    assert client.get("/api/moderator/reports", headers=auth_headers, params={"status": "NOPE"}).status_code == 422
    bad_range = {"created_from": "2030-02-01", "created_to": "2030-01-01"}
    assert client.get("/api/moderator/reports", headers=auth_headers, params=bad_range).status_code == 422


def test_pagination(client, auth_headers, create_report):
    created = [create_report(description=f"Report number {i} with enough text.") for i in range(5)]

    def page(n):
        response = client.get("/api/moderator/reports", headers=auth_headers, params={"page": n, "page_size": 2})
        assert response.status_code == 200
        return response.json()["data"]

    first, second, third, fourth = page(1), page(2), page(3), page(4)
    assert (first["total"], first["pages"], first["page_size"]) == (5, 3, 2)
    assert [len(p["items"]) for p in (first, second, third, fourth)] == [2, 2, 1, 0]

    seen = [i["case_code"] for p in (first, second, third) for i in p["items"]]
    assert sorted(seen) == sorted(created)  # every report appears exactly once
    assert seen == list(reversed(created))  # newest first

    assert client.get("/api/moderator/reports", headers=auth_headers, params={"page": 0}).status_code == 422
    assert client.get("/api/moderator/reports", headers=auth_headers, params={"page_size": 101}).status_code == 422


def test_stats(client, auth_headers, create_report):
    a = create_report(category="SECURITY")
    create_report(category="TECHNICAL")
    patch_status(client, auth_headers, a, "UNDER_REVIEW")

    data = client.get("/api/moderator/stats", headers=auth_headers).json()["data"]
    assert data["total"] == 2
    assert data["by_status"] == {"SUBMITTED": 1, "UNDER_REVIEW": 1, "RESOLVED": 0, "DISMISSED": 0}
    assert data["by_category"]["SECURITY"] == 1 and data["by_category"]["OTHER"] == 0


def test_workflow_table_matches_documented_lifecycle():
    assert workflow.allowed_transitions(ReportStatus.SUBMITTED) == [ReportStatus.UNDER_REVIEW]
    assert workflow.allowed_transitions(ReportStatus.UNDER_REVIEW) == [ReportStatus.RESOLVED, ReportStatus.DISMISSED]
    assert workflow.allowed_transitions(ReportStatus.RESOLVED) == []
    assert workflow.allowed_transitions(ReportStatus.DISMISSED) == []
