"""Transaction-safe publishing of privacy-safe notification requests."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import User, UserRoleAssignment
from app.domains.notifications.enums import NotificationChannel, NotificationEventType
from app.services.outbox import enqueue_outbox_event

_NOTIFICATION_REQUESTED_EVENT = "notification.requested"


def _deduplication_key(
    *,
    tenant_id: UUID,
    recipient_user_id: UUID,
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
) -> str:
    """Build a stable per-recipient delivery intent identity."""
    return (
        f"notification:{tenant_id}:{recipient_user_id}:"
        f"{notification_event_type.value}:{entity_type}:{entity_id}"
    )


def enqueue_notification_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    recipient_user_id: UUID,
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
    template_key: str,
) -> None:
    """
    Queue one recipient-specific delivery request in the current transaction.

    Payloads contain IDs and controlled labels only. The future delivery worker
    resolves recipient addresses and permitted template data at delivery time.
    """
    enqueue_outbox_event(
        session,
        context=context,
        event_type=_NOTIFICATION_REQUESTED_EVENT,
        aggregate_type=entity_type,
        aggregate_id=str(entity_id),
        deduplication_key=_deduplication_key(
            tenant_id=context.tenant_id,
            recipient_user_id=recipient_user_id,
            notification_event_type=notification_event_type,
            entity_type=entity_type,
            entity_id=entity_id,
        ),
        payload={
            "recipient_user_id": str(recipient_user_id),
            "channel": NotificationChannel.EMAIL.value,
            "notification_event_type": notification_event_type.value,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "template_key": template_key,
        },
    )


async def enqueue_notification_for_subject(
    session: AsyncSession,
    *,
    context: TenantContext,
    subject: str,
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
    template_key: str,
) -> None:
    """Queue a notification only if the internal subject still has a tenant user."""
    recipient_user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == subject,
        )
    )
    if recipient_user_id is None:
        return

    enqueue_notification_request(
        session,
        context=context,
        recipient_user_id=recipient_user_id,
        notification_event_type=notification_event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        template_key=template_key,
    )


async def enqueue_notifications_for_roles(
    session: AsyncSession,
    *,
    context: TenantContext,
    roles: Iterable[Role],
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
    template_key: str,
) -> None:
    """Queue one notification request for each current tenant user in a role."""
    role_values = tuple(set(roles))
    if not role_values:
        return

    recipient_ids = list(
        await session.scalars(
            select(User.id)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .where(
                User.tenant_id == context.tenant_id,
                UserRoleAssignment.role.in_(role_values),
            )
            .distinct()
        )
    )

    for recipient_user_id in recipient_ids:
        enqueue_notification_request(
            session,
            context=context,
            recipient_user_id=recipient_user_id,
            notification_event_type=notification_event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            template_key=template_key,
        )
