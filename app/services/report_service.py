"""All report business logic. Routers stay thin and call into these functions."""
import logging
import math
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, Report, ReportStatus
from app.schemas.report import ReportCreate, ReportDetail, ReportPublic, ReportSummary, Stats
from app.services import workflow
from app.utils.case_code import generate_case_code
from app.utils.errors import AppError
from app.utils.time import utcnow

logger = logging.getLogger("whistledrop")

MAX_CODE_ATTEMPTS = 5


def create_report(db: Session, payload: ReportCreate) -> Report:
    """Store a report under a fresh random case code. Retries on the (very unlikely) collision."""
    for _ in range(MAX_CODE_ATTEMPTS):
        now = utcnow()
        report = Report(
            case_code=generate_case_code(),
            category=payload.category.value,
            description=payload.description,
            evidence_url=str(payload.evidence_url) if payload.evidence_url else None,
            status=ReportStatus.SUBMITTED.value,
            created_at=now,
            updated_at=now,
        )
        db.add(report)
        try:
            db.commit()
        except IntegrityError:  # unique index on case_code rejected a duplicate
            db.rollback()
            continue
        logger.info("Report created")  # deliberately no content, no case code
        return report
    raise AppError(500, "case_code_generation_failed", "Could not create the report. Please try again.")


def get_by_case_code(db: Session, case_code: str) -> Report:
    report = db.scalar(select(Report).where(Report.case_code == case_code))
    if report is None:
        raise AppError(404, "report_not_found", "No report found for this case code.")
    return report


def update_status(db: Session, report: Report, new_status: ReportStatus, message: str | None) -> Report:
    current = ReportStatus(report.status)
    if new_status == current:
        # Same status: only allowed as a message-only update, and the message is then required.
        if message is None:
            raise AppError(
                422,
                "message_required",
                "The status is unchanged, so a status update message is required.",
            )
    else:
        workflow.validate_transition(current, new_status)

    report.status = new_status.value
    report.status_message = message
    report.updated_at = utcnow()
    db.commit()
    return report


def list_reports(
    db: Session,
    *,
    category: Category | None,
    status: ReportStatus | None,
    q: str | None,
    created_from: date | None,
    created_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[Report], int]:
    if created_from and created_to and created_from > created_to:
        raise AppError(422, "invalid_date_range", "created_from must not be after created_to.")

    conditions = []
    if category:
        conditions.append(Report.category == category.value)
    if status:
        conditions.append(Report.status == status.value)
    if q:
        term = q.strip()
        conditions.append(
            or_(
                Report.case_code.icontains(term, autoescape=True),
                Report.description.icontains(term, autoescape=True),
            )
        )
    if created_from:
        conditions.append(Report.created_at >= datetime.combine(created_from, time.min, tzinfo=timezone.utc))
    if created_to:  # inclusive of the whole end day
        end = datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        conditions.append(Report.created_at < end)

    total = db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0
    items = db.scalars(
        select(Report)
        .where(*conditions)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def pages_for(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0


def get_stats(db: Session) -> Stats:
    by_status = {s.value: 0 for s in ReportStatus}
    for status, count in db.execute(select(Report.status, func.count()).group_by(Report.status)):
        by_status[status] = count
    by_category = {c.value: 0 for c in Category}
    for category, count in db.execute(select(Report.category, func.count()).group_by(Report.category)):
        by_category[category] = count
    return Stats(total=sum(by_status.values()), by_status=by_status, by_category=by_category)


# ---- mapping database rows to API shapes (the only place fields are chosen) ----

def to_public(report: Report) -> ReportPublic:
    status = ReportStatus(report.status)
    return ReportPublic(
        case_code=report.case_code,
        status=status,
        update=report.status_message or workflow.DEFAULT_UPDATES[status],
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def to_summary(report: Report) -> ReportSummary:
    return ReportSummary(
        case_code=report.case_code,
        category=Category(report.category),
        status=ReportStatus(report.status),
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def to_detail(report: Report) -> ReportDetail:
    status = ReportStatus(report.status)
    return ReportDetail(
        case_code=report.case_code,
        category=Category(report.category),
        description=report.description,
        evidence_url=report.evidence_url,
        status=status,
        status_message=report.status_message,
        allowed_transitions=workflow.allowed_transitions(status),
        created_at=report.created_at,
        updated_at=report.updated_at,
    )
