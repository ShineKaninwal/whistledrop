from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_moderator
from app.database import get_db
from app.models import Category, ReportStatus
from app.routers.reports import valid_case_code
from app.schemas.common import ApiResponse, ErrorResponse, Page
from app.schemas.report import ReportDetail, ReportSummary, Stats, StatusUpdate
from app.services import report_service
from app.utils.responses import ok

AUTH_ERRORS = {401: {"model": ErrorResponse, "description": "Missing, invalid or expired token."}}

router = APIRouter(
    prefix="/api/moderator",
    tags=["Moderator (JWT required)"],
    dependencies=[Depends(get_current_moderator)],
    responses=AUTH_ERRORS,
)


@router.get(
    "/reports",
    response_model=ApiResponse[Page[ReportSummary]],
    summary="List reports",
    description="Newest first. Combine any filters; results are paginated.",
    responses={422: {"model": ErrorResponse, "description": "Invalid filter or pagination value."}},
)
def list_reports(
    category: Category | None = Query(None, description="Filter by category."),
    status: ReportStatus | None = Query(None, description="Filter by status."),
    q: str | None = Query(None, min_length=1, max_length=100, description="Search case code or description."),
    created_from: date | None = Query(None, description="Created on or after this UTC date (YYYY-MM-DD)."),
    created_to: date | None = Query(None, description="Created on or before this UTC date (YYYY-MM-DD)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    reports, total = report_service.list_reports(
        db,
        category=category,
        status=status,
        q=q,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(
        Page[ReportSummary](
            items=[report_service.to_summary(r) for r in reports],
            page=page,
            page_size=page_size,
            total=total,
            pages=report_service.pages_for(total, page_size),
        )
    )


@router.get(
    "/stats",
    response_model=ApiResponse[Stats],
    summary="Dashboard statistics",
    description="Totals overall, per status and per category.",
)
def get_stats(db: Session = Depends(get_db)):
    return ok(report_service.get_stats(db))


@router.get(
    "/reports/{case_code}",
    response_model=ApiResponse[ReportDetail],
    summary="View one report",
    responses={
        404: {"model": ErrorResponse, "description": "No report with this case code."},
        422: {"model": ErrorResponse, "description": "Malformed case code."},
    },
)
def get_report(case_code: str = Depends(valid_case_code), db: Session = Depends(get_db)):
    return ok(report_service.to_detail(report_service.get_by_case_code(db, case_code)))


@router.patch(
    "/reports/{case_code}/status",
    response_model=ApiResponse[ReportDetail],
    summary="Update status and status message",
    description=(
        "Allowed transitions: `SUBMITTED -> UNDER_REVIEW -> RESOLVED | DISMISSED`. "
        "Skipping a step or leaving a final status returns **409**. "
        "Sending the *current* status with a message edits only the message. "
        "The message is what the reporter sees when they check their case code."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "No report with this case code."},
        409: {"model": ErrorResponse, "description": "Invalid status transition."},
        422: {"model": ErrorResponse, "description": "Invalid status, message or case code."},
    },
)
def update_report_status(
    payload: StatusUpdate,
    case_code: str = Depends(valid_case_code),
    db: Session = Depends(get_db),
):
    report = report_service.get_by_case_code(db, case_code)
    report = report_service.update_status(db, report, payload.status, payload.message)
    return ok(report_service.to_detail(report))
