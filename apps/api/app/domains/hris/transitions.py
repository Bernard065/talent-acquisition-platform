"""Pure lifecycle rules for durable HRIS handoffs."""

from app.domains.hris.enums import HrisHandoffStatus


class InvalidHrisHandoffTransitionError(ValueError):
    """Raised when an HRIS handoff lifecycle change is not allowed."""


_ALLOWED_TRANSITIONS: dict[
    HrisHandoffStatus,
    frozenset[HrisHandoffStatus],
] = {
    HrisHandoffStatus.PENDING: frozenset(
        {
            HrisHandoffStatus.PROCESSING,
            HrisHandoffStatus.FAILED,
        }
    ),
    HrisHandoffStatus.PROCESSING: frozenset(
        {
            HrisHandoffStatus.SUCCEEDED,
            HrisHandoffStatus.RETRYABLE_FAILED,
            HrisHandoffStatus.FAILED,
        }
    ),
    HrisHandoffStatus.RETRYABLE_FAILED: frozenset(
        {
            HrisHandoffStatus.PROCESSING,
            HrisHandoffStatus.FAILED,
        }
    ),
    HrisHandoffStatus.SUCCEEDED: frozenset(),
    HrisHandoffStatus.FAILED: frozenset(),
}


def validate_hris_handoff_transition(
    current_status: HrisHandoffStatus,
    target_status: HrisHandoffStatus,
) -> None:
    """Ensure a durable HRIS handoff can make the requested transition."""
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidHrisHandoffTransitionError(
            "Cannot transition HRIS handoff from "
            f"{current_status.value} to {target_status.value}."
        )
