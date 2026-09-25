"""Pure tests for candidate retention interval validation and date rules."""

from datetime import UTC, datetime

import pytest

from app.domains.candidates.retention import (
    CandidateRetentionIntervals,
    retention_review_after,
)


def test_proposed_intervals_are_explicitly_configuration_defaults() -> None:
    intervals = CandidateRetentionIntervals()

    assert intervals.unsuccessful_applicant_days == 365
    assert intervals.withdrawn_applicant_days == 365
    assert intervals.talent_pool_days == 365
    assert intervals.hired_recruiting_copy_days == 90


@pytest.mark.parametrize("days", [0, -1, 3651])
def test_rejects_out_of_range_retention_intervals(days: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 3650"):
        CandidateRetentionIntervals(unsuccessful_applicant_days=days)


def test_review_date_uses_utc_and_does_not_imply_deletion() -> None:
    outcome_at = datetime(2025, 1, 1, tzinfo=UTC)

    assert retention_review_after(outcome_at, 365) == datetime(2026, 1, 1, tzinfo=UTC)


def test_review_date_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        retention_review_after(datetime(2025, 1, 1), 365)
