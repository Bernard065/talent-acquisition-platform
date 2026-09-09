"""Strict HTTP contracts for private offer workflow operations."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.offers.enums import OfferPayPeriod, OfferStatus


class CreateOfferRequest(BaseModel):
    """Private compensation input for creating a draft offer."""

    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3)
    base_salary: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    pay_period: OfferPayPeriod
    bonus_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    equity_summary: str | None = Field(default=None, max_length=5000)
    proposed_start_date: date
    expires_at: datetime

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        """Normalize and validate a three-letter currency code."""
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must contain exactly three letters.")
        return normalized


class ExpectedOfferVersionRequest(BaseModel):
    """Concurrency precondition for an offer mutation."""

    model_config = ConfigDict(extra="forbid")

    expected_offer_version: int = Field(ge=1)


class OfferApprovalDecisionRequest(ExpectedOfferVersionRequest):
    """One assigned approver's decision."""

    decision: ApprovalDecisionStatus
    comment: str | None = Field(default=None, max_length=5000)

    @field_validator("decision")
    @classmethod
    def decision_must_be_final(
        cls,
        value: ApprovalDecisionStatus,
    ) -> ApprovalDecisionStatus:
        """Reject the non-decision pending value at the API boundary."""
        if value is ApprovalDecisionStatus.PENDING:
            raise ValueError("decision must be approved or rejected.")
        return value


class OfferResponse(BaseModel):
    """Private offer metadata and compensation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    status: OfferStatus
    currency: str
    base_salary: Decimal
    pay_period: OfferPayPeriod
    bonus_amount: Decimal | None
    equity_summary: str | None
    proposed_start_date: date
    expires_at: datetime
    approval_requested_at: datetime | None
    approved_at: datetime | None
    sent_at: datetime | None
    accepted_at: datetime | None
    declined_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class OfferApprovalResponse(BaseModel):
    """Private state of a submitted offer approval attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    offer_id: UUID
    attempt: int
    status: ApprovalStatus
    current_step: int
    submitted_at: datetime
    completed_at: datetime | None
