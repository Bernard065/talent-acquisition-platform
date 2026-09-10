"""Pure tests for public job posting lifecycle rules."""

import pytest

from app.domains.job_postings.enums import JobPostingStatus
from app.domains.job_postings.transitions import (
    InvalidJobPostingTransition,
    validate_job_posting_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobPostingStatus.DRAFT, JobPostingStatus.PUBLISHED),
        (JobPostingStatus.PUBLISHED, JobPostingStatus.UNPUBLISHED),
        (JobPostingStatus.PUBLISHED, JobPostingStatus.EXPIRED),
        (JobPostingStatus.UNPUBLISHED, JobPostingStatus.PUBLISHED),
    ],
)
def test_allows_explicit_job_posting_transitions(
    current: JobPostingStatus,
    target: JobPostingStatus,
) -> None:
    """Allow only the documented public-visibility lifecycle changes."""
    validate_job_posting_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobPostingStatus.DRAFT, JobPostingStatus.UNPUBLISHED),
        (JobPostingStatus.DRAFT, JobPostingStatus.EXPIRED),
        (JobPostingStatus.PUBLISHED, JobPostingStatus.DRAFT),
        (JobPostingStatus.UNPUBLISHED, JobPostingStatus.EXPIRED),
        (JobPostingStatus.EXPIRED, JobPostingStatus.PUBLISHED),
    ],
)
def test_rejects_invalid_job_posting_transitions(
    current: JobPostingStatus,
    target: JobPostingStatus,
) -> None:
    """Terminal and unsupported lifecycle changes must be impossible."""
    with pytest.raises(InvalidJobPostingTransition):
        validate_job_posting_transition(current, target)
