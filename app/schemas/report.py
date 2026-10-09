from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.enums import Category, ReportStatus


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


class ReportCreate(BaseModel):
    """Body of an anonymous report. Unknown fields (e.g. "email") are rejected on purpose."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Category = Field(description="One of SECURITY, HARASSMENT, CORRUPTION, TECHNICAL, OTHER.")
    description: str = Field(min_length=10, max_length=5000, description="What happened (10-5000 characters).")
    evidence_url: HttpUrl | None = Field(
        default=None, description="Optional http(s) link to supporting evidence."
    )

    @field_validator("category", mode="before")
    @classmethod
    def _category_case(cls, value):
        return _upper(value)

    @field_validator("evidence_url", mode="before")
    @classmethod
    def _blank_url_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ReportCreated(BaseModel):
    case_code: str = Field(examples=["WD-7K4P9X2M"])
    status: ReportStatus
    message: str
    created_at: datetime


class ReportPublic(BaseModel):
    """Everything a reporter is allowed to see about their own report."""

    case_code: str = Field(examples=["WD-7K4P9X2M"])
    status: ReportStatus
    update: str = Field(examples=["Your report is being reviewed."])
    created_at: datetime
    updated_at: datetime


class ReportSummary(BaseModel):
    """One row in the moderator list."""

    case_code: str
    category: Category
    status: ReportStatus
    created_at: datetime
    updated_at: datetime


class ReportDetail(BaseModel):
    """Full report for moderators."""

    case_code: str
    category: Category
    description: str
    evidence_url: str | None
    status: ReportStatus
    status_message: str | None
    allowed_transitions: list[ReportStatus]
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ReportStatus
    message: str | None = Field(
        default=None, max_length=500, description="Short update shown to the reporter (max 500 characters)."
    )

    @field_validator("status", mode="before")
    @classmethod
    def _status_case(cls, value):
        return _upper(value)

    @field_validator("message", mode="before")
    @classmethod
    def _blank_message_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class Stats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
