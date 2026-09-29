"""Unit tests for privacy-safe notification email rendering."""

from uuid import uuid4

import pytest

from app.domains.notifications.enums import NotificationEventType
from app.services.notification_email_templates import (
    UnsupportedNotificationTemplateError,
    render_notification_email,
)


@pytest.mark.parametrize(
    ("event_type", "template_key", "subject", "text_body"),
    [
        (
            NotificationEventType.OFFER_APPROVAL_REQUESTED,
            "offer_approval_requested",
            "Offer review requested",
            "An offer is ready for your review in the Talent Acquisition Platform.\n\n"
            "Sign in to review the offer and record your decision.",
        ),
        (
            NotificationEventType.OFFER_APPROVED,
            "offer_approved",
            "Offer approval complete",
            "An offer has completed its approval workflow.\n\n"
            "Sign in to the Talent Acquisition Platform to review its current status.",
        ),
        (
            NotificationEventType.OFFER_SENT,
            "offer_sent",
            "Offer update",
            "An offer has been sent to a candidate.\n\n"
            "Sign in to the Talent Acquisition Platform to review its status.",
        ),
        (
            NotificationEventType.OFFER_ACCEPTED,
            "offer_accepted",
            "Offer accepted",
            "A candidate has accepted an offer.\n\n"
            "Sign in to the Talent Acquisition Platform to review the hiring workflow.",
        ),
        (
            NotificationEventType.ONBOARDING_STARTED,
            "onboarding_started",
            "Onboarding started",
            "An onboarding workflow has started.\n\n"
            "Sign in to the Talent Acquisition Platform to review its tasks.",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_ASSIGNED,
            "onboarding_task_assigned",
            "Onboarding task assigned",
            "A new onboarding task has been assigned to you.\n\n"
            "Sign in to the Talent Acquisition Platform to view the task instructions.",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_BLOCKED,
            "onboarding_task_blocked",
            "Onboarding task needs attention",
            "An onboarding task needs attention.\n\n"
            "Sign in to the Talent Acquisition Platform to review the task.",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_COMPLETED,
            "onboarding_task_completed",
            "Onboarding task completed",
            "An onboarding task has been completed.\n\n"
            "Sign in to the Talent Acquisition Platform for details.",
        ),
    ],
)
def test_renders_each_supported_event_template(
    event_type: NotificationEventType,
    template_key: str,
    subject: str,
    text_body: str,
) -> None:
    """Each allow-listed event has stable, event-specific plain-text copy."""
    notification_id = uuid4()
    idempotency_key = "a" * 64

    message = render_notification_email(
        notification_id=notification_id,
        idempotency_key=idempotency_key,
        recipient_email="recipient@example.test",
        event_type=event_type.value,
        template_key=template_key,
    )

    assert message.notification_id == notification_id
    assert message.idempotency_key == idempotency_key
    assert message.recipient_email == "recipient@example.test"
    assert message.subject == subject
    assert message.text_body == text_body


@pytest.mark.parametrize(
    ("event_type", "template_key"),
    [
        ("offer.sent", "unknown_template"),
        ("offer.sent", "onboarding_started"),
        ("unknown.event", "offer_sent"),
    ],
)
def test_rejects_unknown_or_mismatched_template_pairs(
    event_type: str,
    template_key: str,
) -> None:
    """Unknown keys and event/key mismatches fail closed."""
    with pytest.raises(UnsupportedNotificationTemplateError):
        render_notification_email(
            notification_id=uuid4(),
            idempotency_key="a" * 64,
            recipient_email="recipient@example.test",
            event_type=event_type,
            template_key=template_key,
        )


def test_template_does_not_expose_workflow_identifiers_or_candidate_data() -> None:
    """Rendered copy contains no entity IDs, candidate PII, or private details."""
    notification_id = uuid4()
    entity_id = uuid4()
    candidate_email = "candidate-private@example.test"

    message = render_notification_email(
        notification_id=notification_id,
        idempotency_key="b" * 64,
        recipient_email="recipient@example.test",
        event_type=NotificationEventType.OFFER_SENT.value,
        template_key="offer_sent",
    )

    content = f"{message.subject}\n{message.text_body}"
    assert str(notification_id) not in content
    assert str(entity_id) not in content
    assert candidate_email not in content
    assert "compensation" not in content.lower()
    assert "feedback" not in content.lower()
