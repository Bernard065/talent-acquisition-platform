"""PostgreSQL integration tests for durable notification outbox publishing."""

import re
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.outbox import OutboxEvent
from app.domains.notifications.enums import NotificationEventType
from app.services.notification_publishing import (
    enqueue_notification_for_subject,
    enqueue_notification_request,
    enqueue_notifications_for_roles,
)


def _context(tenant_id: UUID) -> TenantContext:
    """Build a verified internal operational context."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="publisher-subject",
        roles=frozenset({Role.PEOPLE_OPERATIONS}),
        request_id="notification-publishing-test-request-id",
    )


async def _seed_tenant_users(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> dict[str, User]:
    """Create tenant-local users and role assignments."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Notification Tenant {tenant_id.hex[:12]}",
            slug=f"notification-{tenant_id.hex[:12]}",
        )
    )

    users = {
        "publisher": User(
            tenant_id=tenant_id,
            external_subject="publisher-subject",
            email=f"publisher-{tenant_id.hex[:8]}@example.test",
            display_name="Publisher",
        ),
        "recipient": User(
            tenant_id=tenant_id,
            external_subject="recipient-subject",
            email=f"recipient-{tenant_id.hex[:8]}@example.test",
            display_name="Recipient",
        ),
        "people_operations": User(
            tenant_id=tenant_id,
            external_subject="people-operations-subject",
            email=f"peopleops-{tenant_id.hex[:8]}@example.test",
            display_name="People Operations",
        ),
    }
    session.add_all(users.values())
    await session.flush()

    session.add(
        UserRoleAssignment(
            user_id=users["people_operations"].id,
            role=Role.PEOPLE_OPERATIONS,
        )
    )
    await session.commit()

    return users


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notification_event_type", "template_key"),
    [
        (
            NotificationEventType.OFFER_APPROVAL_REQUESTED,
            "offer_approval_requested",
        ),
        (
            NotificationEventType.OFFER_APPROVED,
            "offer_approved",
        ),
        (
            NotificationEventType.OFFER_SENT,
            "offer_sent",
        ),
        (
            NotificationEventType.OFFER_ACCEPTED,
            "offer_accepted",
        ),
        (
            NotificationEventType.ONBOARDING_STARTED,
            "onboarding_started",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_ASSIGNED,
            "onboarding_task_assigned",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_BLOCKED,
            "onboarding_task_blocked",
        ),
        (
            NotificationEventType.ONBOARDING_TASK_COMPLETED,
            "onboarding_task_completed",
        ),
    ],
)
async def test_queues_one_private_notification_event_per_recipient(
    session: AsyncSession,
    notification_event_type: NotificationEventType,
    template_key: str,
) -> None:
    """Persist identifier-only event payloads for every supported workflow event."""
    tenant_id = uuid4()
    users = await _seed_tenant_users(session, tenant_id=tenant_id)
    entity_id = uuid4()

    enqueue_notification_request(
        session,
        context=_context(tenant_id),
        recipient_user_id=users["recipient"].id,
        notification_event_type=notification_event_type,
        entity_type="workflow_entity",
        entity_id=entity_id,
        template_key=template_key,
    )
    await session.commit()

    event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.aggregate_id == str(entity_id),
        )
    )

    assert event is not None
    assert event.event_type == "notification.requested"
    assert event.payload | {
        "notification_deduplication_key": None,
    } == {
        "recipient_user_id": str(users["recipient"].id),
        "channel": "email",
        "notification_event_type": notification_event_type.value,
        "entity_type": "workflow_entity",
        "entity_id": str(entity_id),
        "template_key": template_key,
        "notification_deduplication_key": None,
    }
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        str(event.payload["notification_deduplication_key"]),
    )

    serialized_payload = str(event.payload).lower()
    for prohibited_value in (
        "salary",
        "bonus",
        "equity",
        "candidate",
        "email@example",
        "feedback",
        "description",
        "blocked_reason",
    ):
        assert prohibited_value not in serialized_payload


@pytest.mark.asyncio
async def test_prevents_duplicate_notification_request_for_same_recipient(
    session: AsyncSession,
) -> None:
    """Database uniqueness makes repeat publishing harmless."""
    tenant_id = uuid4()
    users = await _seed_tenant_users(session, tenant_id=tenant_id)
    entity_id = uuid4()

    enqueue_notification_request(
        session,
        context=_context(tenant_id),
        recipient_user_id=users["recipient"].id,
        notification_event_type=NotificationEventType.OFFER_SENT,
        entity_type="offer",
        entity_id=entity_id,
        template_key="offer_sent",
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            enqueue_notification_request(
                session,
                context=_context(tenant_id),
                recipient_user_id=users["recipient"].id,
                notification_event_type=NotificationEventType.OFFER_SENT,
                entity_type="offer",
                entity_id=entity_id,
                template_key="offer_sent",
            )
            await session.flush()

    matching_events = await session.scalars(
        select(OutboxEvent.id).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.aggregate_id == str(entity_id),
        )
    )

    assert len(matching_events.all()) == 1


@pytest.mark.asyncio
async def test_subject_and_role_recipient_resolution_is_tenant_scoped(
    session: AsyncSession,
) -> None:
    """Resolve recipients only from verified tenant-local internal identities."""
    tenant_id = uuid4()
    users = await _seed_tenant_users(session, tenant_id=tenant_id)
    entity_id = uuid4()

    await enqueue_notification_for_subject(
        session,
        context=_context(tenant_id),
        subject="recipient-subject",
        notification_event_type=NotificationEventType.OFFER_ACCEPTED,
        entity_type="offer",
        entity_id=entity_id,
        template_key="offer_accepted",
    )
    await enqueue_notifications_for_roles(
        session,
        context=_context(tenant_id),
        roles=(Role.PEOPLE_OPERATIONS,),
        notification_event_type=NotificationEventType.ONBOARDING_STARTED,
        entity_type="onboarding_instance",
        entity_id=uuid4(),
        template_key="onboarding_started",
    )
    await session.commit()

    recipient_ids = set(
        await session.scalars(
            select(OutboxEvent.payload["recipient_user_id"].astext).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "notification.requested",
            )
        )
    )

    assert recipient_ids == {
        str(users["recipient"].id),
        str(users["people_operations"].id),
    }
