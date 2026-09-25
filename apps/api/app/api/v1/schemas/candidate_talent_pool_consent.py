"""Strict HTTP contracts for candidate talent-pool consent events."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)

ConsentCaptureMethod = Literal[
    CandidateTalentPoolCaptureMethod.SIGNED_FORM,
    CandidateTalentPoolCaptureMethod.EMAIL_CONFIRMATION,
    CandidateTalentPoolCaptureMethod.RECRUITER_RECORDED,
]


class CandidateTalentPoolConsentGrantRequest(BaseModel):
    """Evidence metadata for an explicit candidate consent grant or renewal."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    notice_version: str = Field(min_length=1, max_length=100)
    capture_method: ConsentCaptureMethod


class CandidateTalentPoolConsentWithdrawalRequest(BaseModel):
    """Controlled provenance for a candidate-requested withdrawal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    capture_method: ConsentCaptureMethod


class CandidateTalentPoolConsentResponse(BaseModel):
    """PII-minimized acknowledgment for one consent lifecycle event."""

    model_config = ConfigDict(extra="forbid", strict=True)

    event_id: UUID
    candidate_id: UUID
    event_version: int
    event_type: CandidateTalentPoolConsentEventType
    capture_method: CandidateTalentPoolCaptureMethod
    notice_version: str | None
    recorded_at: datetime
