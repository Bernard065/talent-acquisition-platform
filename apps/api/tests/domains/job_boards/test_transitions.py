"""Pure transition tests for external job-board publication state."""

import pytest

from app.domains.job_boards.enums import JobBoardPublicationStatus
from app.domains.job_boards.transitions import (
    InvalidJobBoardPublicationTransition,
    validate_job_board_publication_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.PUBLISHED,
        ),
        (
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
            JobBoardPublicationStatus.FAILED,
        ),
        (
            JobBoardPublicationStatus.PUBLISHED,
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.PUBLISHED,
            JobBoardPublicationStatus.FAILED,
        ),
        (
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
            JobBoardPublicationStatus.UNPUBLISHED,
        ),
        (
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
            JobBoardPublicationStatus.FAILED,
        ),
        (
            JobBoardPublicationStatus.UNPUBLISHED,
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.FAILED,
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.FAILED,
            JobBoardPublicationStatus.UNPUBLISH_REQUESTED,
        ),
    ],
)
def test_all_documented_transitions_are_allowed(
    current: JobBoardPublicationStatus,
    target: JobBoardPublicationStatus,
) -> None:
    """Permit only explicitly modeled provider synchronization transitions."""
    validate_job_board_publication_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (status, status)
        for status in JobBoardPublicationStatus
    ]
    + [
        (
            JobBoardPublicationStatus.PUBLISHED,
            JobBoardPublicationStatus.PUBLISH_REQUESTED,
        ),
        (
            JobBoardPublicationStatus.UNPUBLISHED,
            JobBoardPublicationStatus.PUBLISHED,
        ),
        (
            JobBoardPublicationStatus.FAILED,
            JobBoardPublicationStatus.PUBLISHED,
        ),
    ],
)
def test_undocumented_transitions_are_rejected(
    current: JobBoardPublicationStatus,
    target: JobBoardPublicationStatus,
) -> None:
    """State changes cannot skip the durable request and provider result steps."""
    with pytest.raises(InvalidJobBoardPublicationTransition):
        validate_job_board_publication_transition(current, target)
