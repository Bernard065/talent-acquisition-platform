"""Strict private response contracts for talent-pool search."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from email_validator import validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
)


def _validate_email_address(value: str) -> str:
    """Allow RFC 2606 test domains in non-production fixtures while rejecting malformed addresses."""
    validated = validate_email(
        value,
        check_deliverability=False,
        test_environment=True,
    )
    return str(validated.normalized)


class TalentPoolCandidateResponse(BaseModel):
    """Minimum candidate profile and current consent evidence for recruiters."""

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: UUID
    full_name: str
    email: Annotated[str, AfterValidator(_validate_email_address)]
    phone: str | None
    location: str | None
    source: str
    consent_event_version: int = Field(ge=1)
    consent_capture_method: CandidateTalentPoolCaptureMethod
    consent_notice_version: str = Field(min_length=1, max_length=100)
    consent_recorded_at: datetime


class TalentPoolSearchResponse(BaseModel):
    """Strict cursor page of currently consented talent-pool candidates."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[TalentPoolCandidateResponse]
    next_cursor: str | None
