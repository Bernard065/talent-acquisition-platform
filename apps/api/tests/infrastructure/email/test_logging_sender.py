"""Unit tests for the local privacy-safe email adapter."""

from uuid import uuid4

import pytest

from app.infrastructure.email import logging_sender
from app.services.email_sender import EmailMessage


class RecordingLogger:
    """Captures structured event fields without emitting log output."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **kwargs: object) -> None:
        """Capture a structured log event for assertions."""
        self.calls.append((event_name, kwargs))


@pytest.mark.asyncio
async def test_logging_sender_never_logs_recipient_or_rendered_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging must contain only safe operational identifiers."""
    logger = RecordingLogger()
    monkeypatch.setattr(logging_sender, "logger", logger)

    message = EmailMessage(
        notification_id=uuid4(),
        idempotency_key="a" * 64,
        recipient_email="candidate.private@example.test",
        subject="Compensation: KES 500,000",
        text_body=(
            "Private feedback, candidate CV details, task description, "
            "and blocked reason must never enter logs."
        ),
    )

    sender = logging_sender.LoggingEmailSender()
    provider_message_id = await sender.send(message)

    assert provider_message_id == f"local:{'a' * 64}"
    assert len(logger.calls) == 1

    event_name, fields = logger.calls[0]
    serialized = f"{event_name} {fields}".lower()

    assert event_name == "notification_email_accepted"
    assert fields == {
        "notification_id": str(message.notification_id),
        "idempotency_key": message.idempotency_key,
    }
    for prohibited in (
        "candidate.private@example.test",
        "compensation",
        "500,000",
        "feedback",
        "task description",
        "blocked reason",
    ):
        assert prohibited not in serialized
