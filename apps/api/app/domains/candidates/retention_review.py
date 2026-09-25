"""Pure rules for recording human candidate-retention review evidence."""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewReason,
)


class CandidateRetentionReviewInputError(ValueError):
    """Raised when review evidence is incomplete or internally inconsistent."""


class CandidateRetentionReviewIneligibleError(ValueError):
    """Raised when current candidate state blocks an erasure recommendation."""


@dataclass(frozen=True, slots=True)
class CandidateRetentionReviewChecklist:
    """Structured attestations reviewed without storing free-form case notes."""

    active_matters_reviewed: bool
    legal_holds_reviewed: bool
    other_lawful_basis_reviewed: bool
    employee_obligations_reviewed: bool
    external_processors_reviewed: bool
    backup_restore_safeguards_reviewed: bool

    @property
    def is_complete(self) -> bool:
        """Whether each required privacy and downstream-retention check is attested."""
        return all(
            (
                self.active_matters_reviewed,
                self.legal_holds_reviewed,
                self.other_lawful_basis_reviewed,
                self.employee_obligations_reviewed,
                self.external_processors_reviewed,
                self.backup_restore_safeguards_reviewed,
            )
        )


def validate_candidate_retention_review(
    *,
    disposition: CandidateRetentionReviewDisposition,
    reason_code: CandidateRetentionReviewReason,
    checklist: CandidateRetentionReviewChecklist,
    reviewed_at: datetime,
    next_review_at: datetime | None,
    has_active_workflow: bool,
    has_active_legal_hold: bool,
) -> tuple[datetime, datetime | None]:
    """Validate a review without triggering or authorizing any deletion.

    A manual-erasure recommendation is evidence for a separate, human-operated
    process only. It requires complete attestations and a candidate state with
    no active workflow or legal hold; this function never mutates candidate
    data or creates deletion work.
    """
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise CandidateRetentionReviewInputError("Review timestamp must be timezone-aware.")
    normalized_reviewed_at = reviewed_at.astimezone(UTC)

    if disposition is CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE:
        if reason_code is not CandidateRetentionReviewReason.REVIEW_COMPLETE:
            raise CandidateRetentionReviewInputError(
                "Erasure consideration requires the review-complete reason code."
            )
        if next_review_at is not None:
            raise CandidateRetentionReviewInputError(
                "A completed erasure-consideration review cannot schedule a retention review."
            )
        if not checklist.is_complete:
            raise CandidateRetentionReviewInputError(
                "All review checklist items are required before recommending manual erasure."
            )
        if has_active_workflow or has_active_legal_hold:
            raise CandidateRetentionReviewIneligibleError(
                "An active workflow or legal hold blocks an erasure recommendation."
            )
        return normalized_reviewed_at, None

    if reason_code is CandidateRetentionReviewReason.REVIEW_COMPLETE:
        raise CandidateRetentionReviewInputError(
            "The review-complete reason is reserved for erasure consideration."
        )
    if next_review_at is None:
        raise CandidateRetentionReviewInputError(
            "Retain and defer decisions require a next review timestamp."
        )
    if next_review_at.tzinfo is None or next_review_at.utcoffset() is None:
        raise CandidateRetentionReviewInputError("Next review timestamp must be timezone-aware.")

    normalized_next_review_at = next_review_at.astimezone(UTC)
    if normalized_next_review_at <= normalized_reviewed_at:
        raise CandidateRetentionReviewInputError(
            "Next review timestamp must be later than the review timestamp."
        )
    return normalized_reviewed_at, normalized_next_review_at
