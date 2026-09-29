"""Pure state-transition rules for external job-board publications."""

from app.domains.job_boards.enums import JobBoardPublicationStatus


class InvalidJobBoardPublicationTransition(ValueError):
    """Raised when a publication state change is not allowed."""


_ALLOWED_TRANSITIONS: dict[
    JobBoardPublicationStatus,
    frozenset[JobBoardPublicationStatus],
] = {
    JobBoardPublicationStatus.PUBLISH_REQUESTED: frozenset(
        {
            JobBoardPublicationStatus.PUBLISHED,
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
            JobBoardPublicationStatus.FAILED,
        }
    ),
    JobBoardPublicationStatus.PUBLISHED: frozenset(
        {
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
            JobBoardPublicationStatus.FAILED,
        }
    ),
    JobBoardPublicationStatus.UNPUBLISH_REQUESTED: frozenset(
        {
            JobBoardPublicationStatus.UNPUBLISHED,
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.FAILED,
        }
    ),
    JobBoardPublicationStatus.UNPUBLISHED: frozenset(
        {JobBoardPublicationStatus.PUBLISH_REQUESTED}
    ),
    JobBoardPublicationStatus.FAILED: frozenset(
        {
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
        }
    ),
}


def validate_job_board_publication_transition(
    current: JobBoardPublicationStatus,
    target: JobBoardPublicationStatus,
) -> None:
    """Reject every state change not explicitly listed in the workflow."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidJobBoardPublicationTransition(
            f"Cannot transition a job-board publication from {current.value} "
            f"to {target.value}."
        )
