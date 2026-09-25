"""Pure validation tests for human candidate-retention review evidence."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domains.candidates.retention_review import (
    CandidateRetentionReviewChecklist,
    CandidateRetentionReviewIneligibleError,
    CandidateRetentionReviewInputError,
    validate_candidate_retention_review,
)
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewReason,
)


def _checklist(*, complete: bool = True) -> CandidateRetentionReviewChecklist:
    return CandidateRetentionReviewChecklist(
        active_matters_reviewed=complete,
        legal_holds_reviewed=complete,
        other_lawful_basis_reviewed=complete,
        employee_obligations_reviewed=complete,
        external_processors_reviewed=complete,
        backup_restore_safeguards_reviewed=complete,
    )


def test_retain_review_requires_a_future_timezone_aware_review_date() -> None:
    reviewed_at = datetime(2026, 9, 25, 9, tzinfo=timezone(timedelta(hours=3)))
    next_review_at = datetime(2027, 9, 25, 6, tzinfo=UTC)

    normalized_reviewed_at, normalized_next_review_at = validate_candidate_retention_review(
        disposition=CandidateRetentionReviewDisposition.RETAIN,
        reason_code=CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS,
        checklist=_checklist(),
        reviewed_at=reviewed_at,
        next_review_at=next_review_at,
        has_active_workflow=False,
        has_active_legal_hold=False,
    )

    assert normalized_reviewed_at == datetime(2026, 9, 25, 6, tzinfo=UTC)
    assert normalized_next_review_at == next_review_at


def test_recommendation_is_non_destructive_and_requires_complete_checks() -> None:
    reviewed_at = datetime(2026, 9, 25, 6, tzinfo=UTC)

    normalized_reviewed_at, next_review_at = validate_candidate_retention_review(
        disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
        reason_code=CandidateRetentionReviewReason.REVIEW_COMPLETE,
        checklist=_checklist(),
        reviewed_at=reviewed_at,
        next_review_at=None,
        has_active_workflow=False,
        has_active_legal_hold=False,
    )

    assert normalized_reviewed_at == reviewed_at
    assert next_review_at is None

    with pytest.raises(CandidateRetentionReviewInputError, match="checklist"):
        validate_candidate_retention_review(
            disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
            reason_code=CandidateRetentionReviewReason.REVIEW_COMPLETE,
            checklist=_checklist(complete=False),
            reviewed_at=reviewed_at,
            next_review_at=None,
            has_active_workflow=False,
            has_active_legal_hold=False,
        )


@pytest.mark.parametrize("active_workflow,active_hold", [(True, False), (False, True)])
def test_recommendation_is_blocked_by_active_workflow_or_legal_hold(
    active_workflow: bool,
    active_hold: bool,
) -> None:
    with pytest.raises(CandidateRetentionReviewIneligibleError):
        validate_candidate_retention_review(
            disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
            reason_code=CandidateRetentionReviewReason.REVIEW_COMPLETE,
            checklist=_checklist(),
            reviewed_at=datetime.now(UTC),
            next_review_at=None,
            has_active_workflow=active_workflow,
            has_active_legal_hold=active_hold,
        )


def test_rejects_naive_review_time_and_non_monotonic_next_review() -> None:
    with pytest.raises(CandidateRetentionReviewInputError, match="timezone-aware"):
        validate_candidate_retention_review(
            disposition=CandidateRetentionReviewDisposition.DEFER,
            reason_code=CandidateRetentionReviewReason.PROCESSOR_ACTION_PENDING,
            checklist=_checklist(),
            reviewed_at=datetime(2026, 9, 25, 6),
            next_review_at=datetime(2027, 9, 25, 6, tzinfo=UTC),
            has_active_workflow=False,
            has_active_legal_hold=False,
        )

    reviewed_at = datetime(2026, 9, 25, 6, tzinfo=UTC)
    with pytest.raises(CandidateRetentionReviewInputError, match="later"):
        validate_candidate_retention_review(
            disposition=CandidateRetentionReviewDisposition.DEFER,
            reason_code=CandidateRetentionReviewReason.BACKUP_RESTORE_REVIEW_PENDING,
            checklist=_checklist(),
            reviewed_at=reviewed_at,
            next_review_at=reviewed_at,
            has_active_workflow=False,
            has_active_legal_hold=False,
        )
