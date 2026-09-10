"""PostgreSQL integration tests for notification intent creation."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import Tenant, User
from app.db.models.notification import Notification, NotificationPreference
from app.db.models.outbox import OutboxEvent
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.domains.outbox.enums import OutboxEventStatus
from app.services.notification_intents import (
    _request_from_event,
    create_notification_intent,
    process_notification_request_events,
)


async def _seed_notification_event(
    session: AsyncSession,
    *,
    payload: dict[str, str] | None = None,
) -> tuple[User, OutboxEvent]:
    """Create one tenant, recipient, and pending notification event."""
    tenant_id = uuid4()
    recipient = User(
        tenant_id=tenant_id,
        external_subject=f"recipient-{tenant_id.hex}",
        email=f"recipient-{tenant_id.hex[:10]}@example.test",
        display_name="Notification Recipient",
    )
    tenant = Tenant(
        id=tenant_id,
        name=f"Notification Tenant {tenant_id.hex[:12]}",
        slug=f"notification-{tenant_id.hex[:12]}",
    )

    session.add(tenant)
    await session.flush()
    session.add(recipient)
    await session.flush()

    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="notification.requested",
        aggregate_type="offer",
        aggregate_id=str(uuid4()),
        deduplication_key=f"notification-event-{uuid4()}",
        payload=payload
        or {
            "recipient_user_id": str(recipient.id),
            "channel": "email",
            "notification_event_type": "offer.sent",
            "entity_type": "offer",
            "entity_id": str(uuid4()),
            "template_key": "offer_sent",
            "notification_deduplication_key": "a" * 64,
        },
    )

    session.add(event)
    await session.commit()

    return recipient, event


@pytest.mark.asyncio
async def test_creates_one_intent_when_the_same_event_is_replayed(
    session: AsyncSession,
) -> None:
    """The notification uniqueness boundary makes event replay harmless."""
    _, event = await _seed_notification_event(session)
    request = _request_from_event(event)

    first = await create_notification_intent(
        session,
        event=event,
        request=request,
    )
    await session.commit()

    second = await create_notification_intent(
        session,
        event=event,
        request=request,
    )
    await session.commit()

    count = len(
        (
            await session.scalars(
                select(Notification.id).where(
                    Notification.tenant_id == event.tenant_id
                )
            )
        ).all()
    )

    assert first.id == second.id
    assert count == 1


@pytest.mark.asyncio
async def test_disabled_preference_creates_cancelled_intent(
    session: AsyncSession,
) -> None:
    """A disabled recipient preference prevents delivery without losing traceability."""
    recipient, event = await _seed_notification_event(session)

    session.add(
        NotificationPreference(
            tenant_id=event.tenant_id,
            user_id=recipient.id,
            event_type="offer.sent",
            channel=NotificationChannel.EMAIL,
            enabled=False,
        )
    )
    await session.commit()

    result = await process_notification_request_events(
        session,
        worker_id="notification-intent-worker",
    )
    await session.refresh(event)

    notification = await session.scalar(
        select(Notification).where(Notification.tenant_id == event.tenant_id)
    )

    assert result.claimed == 1
    assert result.processed == 1
    assert result.dead_lettered == 0
    assert event.status is OutboxEventStatus.PROCESSED
    assert notification is not None
    assert notification.status is NotificationStatus.CANCELLED
    assert notification.cancelled_at is not None


@pytest.mark.asyncio
async def test_dead_letters_malformed_notification_request(
    session: AsyncSession,
) -> None:
    """Malformed events are terminal rather than retried indefinitely."""
    _, event = await _seed_notification_event(
        session,
        payload={"unexpected": "payload"},
    )

    result = await process_notification_request_events(
        session,
        worker_id="notification-intent-worker",
    )
    await session.refresh(event)

    count = len(
        (
            await session.scalars(
                select(Notification.id).where(
                    Notification.tenant_id == event.tenant_id
                )
            )
        ).all()
    )

    assert result.claimed == 1
    assert result.processed == 0
    assert result.dead_lettered == 1
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "invalid_notification_event_payload"
    assert count == 0
