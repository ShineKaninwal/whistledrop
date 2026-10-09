"""The report lifecycle. This table is the single source of truth for allowed status changes.

    SUBMITTED -> UNDER_REVIEW -> RESOLVED
                              -> DISMISSED

A report cannot skip review (SUBMITTED -> RESOLVED is rejected) and RESOLVED / DISMISSED are final.
"""
from app.models.enums import ReportStatus
from app.utils.errors import AppError

TRANSITIONS: dict[ReportStatus, list[ReportStatus]] = {
    ReportStatus.SUBMITTED: [ReportStatus.UNDER_REVIEW],
    ReportStatus.UNDER_REVIEW: [ReportStatus.RESOLVED, ReportStatus.DISMISSED],
    ReportStatus.RESOLVED: [],
    ReportStatus.DISMISSED: [],
}

DEFAULT_UPDATES: dict[ReportStatus, str] = {
    ReportStatus.SUBMITTED: "Your report has been received and is waiting for review.",
    ReportStatus.UNDER_REVIEW: "Your report is being reviewed.",
    ReportStatus.RESOLVED: "Your report has been resolved.",
    ReportStatus.DISMISSED: "Your report was reviewed and closed without further action.",
}


def allowed_transitions(current: ReportStatus) -> list[ReportStatus]:
    return list(TRANSITIONS[current])


def validate_transition(current: ReportStatus, new: ReportStatus) -> None:
    if new not in TRANSITIONS[current]:
        allowed = ", ".join(s.value for s in TRANSITIONS[current]) or "none (this status is final)"
        raise AppError(
            409,
            "invalid_status_transition",
            f"Cannot change status from {current.value} to {new.value}. Allowed: {allowed}.",
        )
