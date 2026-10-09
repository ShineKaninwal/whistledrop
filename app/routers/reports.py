from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.report import ReportCreate, ReportCreated, ReportPublic
from app.services import report_service
from app.utils.case_code import is_valid_case_code, normalize_case_code
from app.utils.errors import AppError
from app.utils.responses import ok

router = APIRouter(prefix="/api/reports", tags=["Reporter (public, anonymous)"])


def valid_case_code(
    case_code: str = Path(description="The case code received when the report was submitted.", examples=["WD-7K4P9X2M"]),
) -> str:
    """Normalises (trim + uppercase) and validates the format before touching the database."""
    code = normalize_case_code(case_code)
    if not is_valid_case_code(code):
        raise AppError(422, "invalid_case_code", "Case codes look like WD-7K4P9X2M.")
    return code


@router.post(
    "",
    status_code=201,
    response_model=ApiResponse[ReportCreated],
    summary="Submit an anonymous report",
    description=(
        "No account, name, email or phone number is required or accepted. "
        "The response contains the **case code**, the only way to check the report later. "
        "It is shown once, so keep it safe."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Malformed JSON."},
        422: {"model": ErrorResponse, "description": "Validation failed (category, description or evidence URL)."},
    },
)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    report = report_service.create_report(db, payload)
    return ok(
        ReportCreated(
            case_code=report.case_code,
            status=report.status,
            message="Save this case code. It is the only way to check your report's status.",
            created_at=report.created_at,
        )
    )


@router.get(
    "/{case_code}",
    response_model=ApiResponse[ReportPublic],
    summary="Check the status of a report",
    description="Returns only what the reporter needs: status, the latest moderator update and timestamps.",
    responses={
        404: {"model": ErrorResponse, "description": "No report with this case code."},
        422: {"model": ErrorResponse, "description": "Malformed case code."},
    },
)
def get_report_status(case_code: str = Depends(valid_case_code), db: Session = Depends(get_db)):
    return ok(report_service.to_public(report_service.get_by_case_code(db, case_code)))
