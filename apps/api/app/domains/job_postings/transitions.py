"""Pure state-transition rules for public job postings."""

from app.domains.job_postings.enums import JobPostingStatus


class InvalidJobPostingTransition(ValueError):
    """Raised when a requested job posting lifecycle change is not allowed."""


_ALLOWED_TRANSITIONS: dict[JobPostingStatus, frozenset[JobPostingStatus]] = {
    JobPostingStatus.DRAFT: frozenset(
        {
            JobPostingStatus.PUBLISHED,
        }
    ),
    JobPostingStatus.PUBLISHED: frozenset(
        {
            JobPostingStatus.UNPUBLISHED,
            JobPostingStatus.EXPIRED,
        }
    ),
    JobPostingStatus.UNPUBLISHED: frozenset(
        {
            JobPostingStatus.PUBLISHED,
        }
    ),
    JobPostingStatus.EXPIRED: frozenset(),
}


def validate_job_posting_transition(
    current: JobPostingStatus,
    target: JobPostingStatus,
) -> None:
    """Reject lifecycle changes outside the explicit state machine."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidJobPostingTransition(
            f"Cannot transition job posting from {current.value} "
            f"to {target.value}."
        )
