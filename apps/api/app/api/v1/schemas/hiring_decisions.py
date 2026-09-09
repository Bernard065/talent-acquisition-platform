"""Strict HTTP contracts for post-interview hiring decisions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.candidates.enums import ApplicationRejectionReason
from app.domains.decisions.enums import HiringDecision


class RecordHiringDecisionRequest(BaseModel):
    """Input for one final application debrief decision."""

    model_config = ConfigDict(extra="forbid")

    decision: HiringDecision
    expected_application_version: int = Field(ge=1)
    rationale: str = Field(min_length=1, max_length=5000)
    rejection_reason: ApplicationRejectionReason | None = None

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "RecordHiringDecisionRequest":
        """Require rejection reasons only for rejection decisions."""
        is_rejection = self.decision is HiringDecision.REJECT

        if is_rejection and self.rejection_reason is None:
            raise ValueError(
                "rejection_reason is required when decision is reject."
            )

        if not is_rejection and self.rejection_reason is not None:
            raise ValueError(
                "rejection_reason is allowed only when decision is reject."
            )

        return self


class HiringDecisionResponse(BaseModel):
    """Private response for the decision maker's submitted debrief."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    decision: HiringDecision
    rationale: str
    rejection_reason: ApplicationRejectionReason | None
    decided_at: datetime
    created_at: datetime
    version: int
