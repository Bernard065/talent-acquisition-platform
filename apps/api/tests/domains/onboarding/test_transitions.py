"""Pure tests for onboarding lifecycle transition rules."""

import pytest

from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskStatus,
)
from app.domains.onboarding.transitions import (
    InvalidOnboardingInstanceTransition,
    InvalidOnboardingTaskTransition,
    validate_instance_transition,
    validate_task_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            OnboardingInstanceStatus.ACTIVE,
            OnboardingInstanceStatus.COMPLETED,
        ),
        (
            OnboardingInstanceStatus.ACTIVE,
            OnboardingInstanceStatus.CANCELLED,
        ),
    ],
)
def test_allows_valid_instance_transitions(
    current: OnboardingInstanceStatus,
    target: OnboardingInstanceStatus,
) -> None:
    """Allow only explicit active-instance terminal transitions."""
    validate_instance_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            OnboardingInstanceStatus.ACTIVE,
            OnboardingInstanceStatus.ACTIVE,
        ),
        (
            OnboardingInstanceStatus.COMPLETED,
            OnboardingInstanceStatus.CANCELLED,
        ),
        (
            OnboardingInstanceStatus.CANCELLED,
            OnboardingInstanceStatus.COMPLETED,
        ),
    ],
)
def test_rejects_invalid_instance_transitions(
    current: OnboardingInstanceStatus,
    target: OnboardingInstanceStatus,
) -> None:
    """Completed and cancelled instances remain terminal."""
    with pytest.raises(InvalidOnboardingInstanceTransition):
        validate_instance_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            OnboardingTaskStatus.NOT_STARTED,
            OnboardingTaskStatus.IN_PROGRESS,
        ),
        (
            OnboardingTaskStatus.NOT_STARTED,
            OnboardingTaskStatus.BLOCKED,
        ),
        (
            OnboardingTaskStatus.IN_PROGRESS,
            OnboardingTaskStatus.COMPLETED,
        ),
        (
            OnboardingTaskStatus.BLOCKED,
            OnboardingTaskStatus.IN_PROGRESS,
        ),
        (
            OnboardingTaskStatus.BLOCKED,
            OnboardingTaskStatus.CANCELLED,
        ),
    ],
)
def test_allows_valid_task_transitions(
    current: OnboardingTaskStatus,
    target: OnboardingTaskStatus,
) -> None:
    """Allow only explicit task state-machine transitions."""
    validate_task_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (
            OnboardingTaskStatus.NOT_STARTED,
            OnboardingTaskStatus.COMPLETED,
        ),
        (
            OnboardingTaskStatus.IN_PROGRESS,
            OnboardingTaskStatus.NOT_STARTED,
        ),
        (
            OnboardingTaskStatus.COMPLETED,
            OnboardingTaskStatus.IN_PROGRESS,
        ),
        (
            OnboardingTaskStatus.CANCELLED,
            OnboardingTaskStatus.IN_PROGRESS,
        ),
    ],
)
def test_rejects_invalid_task_transitions(
    current: OnboardingTaskStatus,
    target: OnboardingTaskStatus,
) -> None:
    """Terminal tasks cannot be reopened or bypass required stages."""
    with pytest.raises(InvalidOnboardingTaskTransition):
        validate_task_transition(current, target)
