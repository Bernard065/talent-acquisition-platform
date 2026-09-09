"""Pure onboarding lifecycle transition rules."""

from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskStatus,
)

_INSTANCE_TRANSITIONS: dict[
    OnboardingInstanceStatus,
    frozenset[OnboardingInstanceStatus],
] = {
    OnboardingInstanceStatus.ACTIVE: frozenset(
        {
            OnboardingInstanceStatus.COMPLETED,
            OnboardingInstanceStatus.CANCELLED,
        }
    ),
    OnboardingInstanceStatus.COMPLETED: frozenset(),
    OnboardingInstanceStatus.CANCELLED: frozenset(),
}

_TASK_TRANSITIONS: dict[
    OnboardingTaskStatus,
    frozenset[OnboardingTaskStatus],
] = {
    OnboardingTaskStatus.NOT_STARTED: frozenset(
        {
            OnboardingTaskStatus.IN_PROGRESS,
            OnboardingTaskStatus.BLOCKED,
            OnboardingTaskStatus.CANCELLED,
        }
    ),
    OnboardingTaskStatus.IN_PROGRESS: frozenset(
        {
            OnboardingTaskStatus.COMPLETED,
            OnboardingTaskStatus.BLOCKED,
            OnboardingTaskStatus.CANCELLED,
        }
    ),
    OnboardingTaskStatus.BLOCKED: frozenset(
        {
            OnboardingTaskStatus.IN_PROGRESS,
            OnboardingTaskStatus.CANCELLED,
        }
    ),
    OnboardingTaskStatus.COMPLETED: frozenset(),
    OnboardingTaskStatus.CANCELLED: frozenset(),
}


class InvalidOnboardingInstanceTransition(ValueError):
    """Raised when an onboarding instance transition is not allowed."""


class InvalidOnboardingTaskTransition(ValueError):
    """Raised when an onboarding task transition is not allowed."""


def validate_instance_transition(
    current_status: OnboardingInstanceStatus,
    target_status: OnboardingInstanceStatus,
) -> None:
    """Reject instance lifecycle transitions outside the explicit state machine."""
    if target_status not in _INSTANCE_TRANSITIONS[current_status]:
        raise InvalidOnboardingInstanceTransition(
            f"Cannot transition onboarding instance from {current_status.value} "
            f"to {target_status.value}."
        )


def validate_task_transition(
    current_status: OnboardingTaskStatus,
    target_status: OnboardingTaskStatus,
) -> None:
    """Reject task lifecycle transitions outside the explicit state machine."""
    if target_status not in _TASK_TRANSITIONS[current_status]:
        raise InvalidOnboardingTaskTransition(
            f"Cannot transition onboarding task from {current_status.value} "
            f"to {target_status.value}."
        )
