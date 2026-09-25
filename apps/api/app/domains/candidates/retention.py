"""Review-first retention policy rules for candidate records."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

PROPOSED_UNSUCCESSFUL_DAYS = 365
PROPOSED_WITHDRAWN_DAYS = 365
PROPOSED_TALENT_POOL_DAYS = 365
PROPOSED_HIRED_RECRUITING_COPY_DAYS = 90
MAX_RETENTION_DAYS = 3650


@dataclass(frozen=True, slots=True)
class CandidateRetentionIntervals:
    """Retention durations; these are proposed values, not legal mandates."""

    unsuccessful_applicant_days: int = PROPOSED_UNSUCCESSFUL_DAYS
    withdrawn_applicant_days: int = PROPOSED_WITHDRAWN_DAYS
    talent_pool_days: int = PROPOSED_TALENT_POOL_DAYS
    hired_recruiting_copy_days: int = PROPOSED_HIRED_RECRUITING_COPY_DAYS

    def __post_init__(self) -> None:
        for days in (
            self.unsuccessful_applicant_days,
            self.withdrawn_applicant_days,
            self.talent_pool_days,
            self.hired_recruiting_copy_days,
        ):
            if not 1 <= days <= MAX_RETENTION_DAYS:
                raise ValueError("Retention intervals must be between 1 and 3650 days.")


def retention_review_after(outcome_at: datetime, retention_days: int) -> datetime:
    """Return the earliest review date, never an automatic-delete date."""
    if outcome_at.tzinfo is None or outcome_at.utcoffset() is None:
        raise ValueError("Retention outcome timestamps must be timezone-aware.")
    if not 1 <= retention_days <= MAX_RETENTION_DAYS:
        raise ValueError("Retention interval must be between 1 and 3650 days.")
    return outcome_at.astimezone(UTC) + timedelta(days=retention_days)
