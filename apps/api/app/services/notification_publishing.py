"""Transaction-safe publishing of privacy-safe notification requests."""

from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
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
    recipient_identity: str,
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
    occurrence_key: str | None = None,
) -> str:
    """Return a fixed-length, non-sensitive stable delivery identity."""
    identity = "|".join(
        (
            str(tenant_id),
            recipient_identity,
            notification_event_type.value,
            entity_type,
            str(entity_id),
            *([occurrence_key] if occurrence_key is not None else []),
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()


def enqueue_notification_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    recipient_user_id: UUID | None = None,
    recipient_candidate_id: UUID | None = None,
    notification_event_type: NotificationEventType,
    entity_type: str,
    entity_id: UUID,
    template_key: str,
    occurrence_key: int | None = None,
    scheduled_at: datetime | None = None,
) -> None:
    """Queue one recipient-specific notification request in this transaction."""
    if (recipient_user_id is None) == (recipient_candidate_id is None):
        raise ValueError("Exactly one notification recipient must be provided.")

    recipient_identity = (
        str(recipient_user_id)
        if recipient_user_id is not None
        else f"candidate:{recipient_candidate_id}"
    )
    deduplication_key = _deduplication_key(
        tenant_id=context.tenant_id,
        recipient_identity=recipient_identity,
        notification_event_type=notification_event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        occurrence_key=(
            str(occurrence_key) if occurrence_key is not None else None
        ),
    )

    payload: dict[str, str] = {
        "channel": NotificationChannel.EMAIL.value,
        "notification_event_type": notification_event_type.value,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "template_key": template_key,
        "notification_deduplication_key": deduplication_key,
    }
    if recipient_user_id is not None:
        payload["recipient_user_id"] = str(recipient_user_id)
    if recipient_candidate_id is not None:
        payload["recipient_candidate_id"] = str(recipient_candidate_id)
    if occurrence_key is not None:
        payload["occurrence_key"] = str(occurrence_key)
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at.isoformat()

    enqueue_outbox_event(
        session,
        context=context,
        event_type=_NOTIFICATION_REQUESTED_EVENT,
        aggregate_type=entity_type,
        aggregate_id=str(entity_id),
        deduplication_key=f"notification:{deduplication_key}",
        payload=payload,
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
    """Queue a notification when the subject has an internal tenant user."""
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
    """Queue one notification per current tenant user with an eligible role."""
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
