"""Strict, PII-minimized contracts for candidate retention-review evidence."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewPurpose,
    CandidateRetentionReviewReason,
)


class CandidateRetentionReviewChecklistRequest(BaseModel):
    """Structured attestations; free-form case notes are intentionally excluded."""

    model_config = ConfigDict(extra="forbid")

    active_matters_reviewed: StrictBool
    legal_holds_reviewed: StrictBool
    other_lawful_basis_reviewed: StrictBool
    employee_obligations_reviewed: StrictBool
    external_processors_reviewed: StrictBool
    backup_restore_safeguards_reviewed: StrictBool


class CandidateRetentionReviewCreateRequest(BaseModel):
    """Data required to append a non-destructive human review record."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    policy_id: UUID
    purpose: CandidateRetentionReviewPurpose
    disposition: CandidateRetentionReviewDisposition
    reason_code: CandidateRetentionReviewReason
    checklist: CandidateRetentionReviewChecklistRequest
    next_review_at: datetime | None = None


class CandidateRetentionReviewChecklistResponse(BaseModel):
    """Recorded attestations without candidate profile attributes."""

    model_config = ConfigDict(extra="forbid", strict=True)

    active_matters_reviewed: bool
    legal_holds_reviewed: bool
    other_lawful_basis_reviewed: bool
    employee_obligations_reviewed: bool
    external_processors_reviewed: bool
    backup_restore_safeguards_reviewed: bool


class CandidateRetentionReviewResponse(BaseModel):
    """Immutable review evidence and policy snapshot, excluding candidate PII."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    candidate_id: UUID
    policy_id: UUID
    policy_version: int = Field(ge=1)
    unsuccessful_applicant_days: int = Field(ge=1, le=3650)
    withdrawn_applicant_days: int = Field(ge=1, le=3650)
    talent_pool_days: int = Field(ge=1, le=3650)
    hired_recruiting_copy_days: int = Field(ge=1, le=3650)
    review_number: int = Field(ge=1)
    purpose: CandidateRetentionReviewPurpose
    disposition: CandidateRetentionReviewDisposition
    reason_code: CandidateRetentionReviewReason
    checklist: CandidateRetentionReviewChecklistResponse
    reviewed_by_subject: str = Field(min_length=1, max_length=255)
    reviewed_at: datetime
    next_review_at: datetime | None


class CandidateRetentionReviewListResponse(BaseModel):
    """One tenant-private page of candidate retention-review history."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[CandidateRetentionReviewResponse]
    next_cursor: str | None = None


class CandidateRetentionExecutionRequest(BaseModel):
    """Require an explicit confirmation before executing an erasure review."""

    model_config = ConfigDict(extra="forbid", strict=True)

    confirm_erasure: Literal[True]


class CandidateRetentionExecutionResponse(BaseModel):
    """PII-minimized evidence that a manual-retention recommendation was executed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    candidate_id: UUID
    review_id: UUID
    review_number: int = Field(ge=1)
    policy_version: int = Field(ge=1)
    executed_by_subject: str = Field(min_length=1, max_length=255)
    executed_at: datetime
