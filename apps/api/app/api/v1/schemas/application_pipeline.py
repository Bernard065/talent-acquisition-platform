"""Strict request schemas for application pipeline transitions."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)


class ApplicationStageTransitionRequest(BaseModel):
    """Input for one optimistic-concurrency application stage transition."""

    model_config = ConfigDict(extra="forbid")

    target_status: ApplicationStatus
    expected_version: int = Field(ge=1)
    rejection_reason: ApplicationRejectionReason | None = None

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> Self:
        """Require controlled reasons only when the target stage is rejected."""
        is_rejection = self.target_status is ApplicationStatus.REJECTED

        if is_rejection and self.rejection_reason is None:
            raise ValueError(
                "rejection_reason is required when target_status is rejected."
            )

        if not is_rejection and self.rejection_reason is not None:
            raise ValueError(
                "rejection_reason is allowed only when target_status is rejected."
            )

        return self
