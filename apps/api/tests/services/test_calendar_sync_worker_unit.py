"""Unit tests for calendar-sync worker event parsing and reconciliation."""

from uuid import uuid4

import pytest

from app.db.models.outbox import OutboxEvent
from app.domains.interviews.enums import InterviewSessionStatus
from app.services.calendar_sync_worker import (
    _operation_for_current_session,
    _request_from_event,
)


def _event(payload: dict[str, object]) -> OutboxEvent:
    """Build an in-memory outbox event without database access."""
    return OutboxEvent(
        tenant_id=uuid4(),
        event_type="interview.calendar_sync_requested",
        aggregate_type="interview_session",
        aggregate_id=str(uuid4()),
        deduplication_key=f"test:{uuid4()}",
        payload=payload,
    )


def test_parses_valid_calendar_sync_event() -> None:
    """Accept only the small identifier-only event contract."""
    interview_id = uuid4()

    request = _request_from_event(
        _event(
            {
                "interview_session_id": str(interview_id),
                "operation": "upsert",
                "interview_version": 2,
            }
        )
    )

    assert request.interview_session_id == interview_id
    assert request.operation == "upsert"
    assert request.interview_version == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "interview_session_id": "not-a-uuid",
            "operation": "upsert",
            "interview_version": 1,
        },
        {
            "interview_session_id": str(uuid4()),
            "operation": "create",
            "interview_version": 1,
        },
        {
            "interview_session_id": str(uuid4()),
            "operation": "cancel",
            "interview_version": 0,
        },
    ],
)
def test_rejects_invalid_calendar_sync_event_payload(
    payload: dict[str, object],
) -> None:
    """Malformed events must be dead-lettered by the worker."""
    with pytest.raises((KeyError, TypeError, ValueError)):
        _request_from_event(_event(payload))


def test_current_cancelled_state_wins_over_stale_upsert_event() -> None:
    """A delayed upsert must never recreate a cancelled interview."""
    assert (
        _operation_for_current_session(
            requested_operation="upsert",
            status=InterviewSessionStatus.CANCELLED,
        )
        == "cancel"
    )


def test_completed_session_turns_delayed_upsert_into_noop() -> None:
    """A late event must not create a new calendar record after completion."""
    assert (
        _operation_for_current_session(
            requested_operation="upsert",
            status=InterviewSessionStatus.COMPLETED,
        )
        == "noop"
    )
