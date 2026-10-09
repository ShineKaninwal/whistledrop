"""Optional: add a few clearly fake demo reports so the dashboard is not empty.

    python -m app.seed_demo
"""
from app.database import Base, SessionLocal, engine
from app.models import ReportStatus
from app.schemas.report import ReportCreate
from app.services import report_service
import app.models  # noqa: F401

DEMO_REPORTS = [
    ("SECURITY", "Demo: the admin panel of the club portal is reachable without logging in.", "https://example.com/screenshot-1", None),
    ("HARASSMENT", "Demo: repeated hostile messages in a project group chat after a disagreement.", None, ReportStatus.UNDER_REVIEW),
    ("CORRUPTION", "Demo: event budget invoices appear to be duplicated across two vendors.", "https://example.com/invoice-trail", ReportStatus.UNDER_REVIEW),
    ("TECHNICAL", "Demo: the lab booking form silently drops submissions after 6 PM.", None, None),
    ("OTHER", "Demo: the notice board posts are not updated after events are cancelled.", None, ReportStatus.DISMISSED),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for category, description, url, target in DEMO_REPORTS:
            report = report_service.create_report(
                db, ReportCreate(category=category, description=description, evidence_url=url)
            )
            if target is not None:
                report_service.update_status(db, report, ReportStatus.UNDER_REVIEW, "We are looking into this.")
            if target == ReportStatus.DISMISSED:
                report_service.update_status(db, report, ReportStatus.DISMISSED, "Reviewed; no action needed.")
            print("Created", report.case_code)


if __name__ == "__main__":
    main()
