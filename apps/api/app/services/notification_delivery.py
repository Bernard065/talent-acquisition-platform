"""Leased, idempotent delivery of internal email notification intents."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import User
from app.db.models.notification import Notification
from app.db.transactions import transactional
from app.domains.notifications.enums import NotificationStatus
from app.services.email_sender import EmailDeliveryError, EmailMessage, EmailSender
from app.services.notification_email_templates import (
    UnsupportedNotificationTemplateError,
    render_notification_email,
)


@dataclass(frozen=True, slots=True)
class NotificationDeliveryPolicy:
    """Bounded retry and lease policy for notification delivery."""

    batch_size: int = 10
    max_attempts: int = 8
    visibility_timeout: timedelta = timedelta(minutes=5)
    base_retry_delay: timedelta = timedelta(seconds=30)
    maximum_retry_delay: timedelta = timedelta(hours=1)


DEFAULT_NOTIFICATION_DELIVERY_POLICY = NotificationDeliveryPolicy()


def _now() -> datetime:
    return datetime.now(UTC)


def _retry_delay(attempts: int, policy: NotificationDeliveryPolicy) -> timedelta:
    multiplier = 2 ** max(attempts - 1, 0)
    delay_seconds = policy.base_retry_delay.total_seconds() * multiplier
    maximum_delay_seconds = policy.maximum_retry_delay.total_seconds()
    return timedelta(seconds=min(delay_seconds, maximum_delay_seconds))


async def claim_notifications(
    session: AsyncSession,
    *,
    worker_id: str,
    policy: NotificationDeliveryPolicy = DEFAULT_NOTIFICATION_DELIVERY_POLICY,
    idempotency_retry_window: timedelta | None = None,
) -> list[Notification]:
    """Recover stale leases and claim a bounded, non-overlapping batch."""
    now = _now()
    stale_before = now - policy.visibility_timeout

    async with transactional(session):
        if idempotency_retry_window is not None:
            retry_window_expired_before = now - idempotency_retry_window
            await session.execute(
                update(Notification)
                .where(
                    Notification.status.in_(
                        [NotificationStatus.PENDING, NotificationStatus.SENDING]
                    ),
                    Notification.first_delivery_attempt_at.is_not(None),
                    Notification.first_delivery_attempt_at <= retry_window_expired_before,
                )
                .values(
                    status=NotificationStatus.FAILED,
                    failed_at=now,
                    locked_at=None,
                    locked_by=None,
                    last_error_code="provider_idempotency_window_expired",
                    updated_at=now,
                )
            )

        await session.execute(
            update(Notification)
            .where(
                Notification.status == NotificationStatus.SENDING,
                Notification.locked_at.is_not(None),
                Notification.locked_at < stale_before,
                Notification.attempts >= policy.max_attempts,
            )
            .values(
                status=NotificationStatus.FAILED,
                failed_at=now,
                locked_at=None,
                locked_by=None,
                last_error_code="lease_expired",
            )
        )
        await session.execute(
            update(Notification)
            .where(
                Notification.status == NotificationStatus.SENDING,
                Notification.locked_at.is_not(None),
                Notification.locked_at < stale_before,
                Notification.attempts < policy.max_attempts,
            )
            .values(
                status=NotificationStatus.PENDING,
                locked_at=None,
                locked_by=None,
                next_attempt_at=now,
                last_error_code="lease_expired",
            )
        )

        notifications = list(
            await session.scalars(
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.PENDING,
                    Notification.next_attempt_at <= now,
                )
                .order_by(
                    Notification.next_attempt_at,
                    Notification.created_at,
                    Notification.id,
                )
                .with_for_update(skip_locked=True)
                .limit(policy.batch_size)
            )
        )

        for notification in notifications:
            notification.status = NotificationStatus.SENDING
            notification.locked_at = now
            notification.locked_by = worker_id
            notification.attempts += 1
            if notification.first_delivery_attempt_at is None:
                notification.first_delivery_attempt_at = now

        await session.flush()

    return notifications


async def _get_leased_notification(
    session: AsyncSession,
    *,
    notification_id: UUID,
    worker_id: str,
) -> Notification:
    notification = await session.scalar(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    )
    if notification is None:
        raise LookupError("Notification was not found.")

    if notification.status != NotificationStatus.SENDING or notification.locked_by != worker_id:
        raise RuntimeError("Notification lease was lost.")

    return notification


async def mark_notification_sent(
    session: AsyncSession,
    *,
    notification_id: UUID,
    worker_id: str,
    provider_message_id: str,
) -> None:
    """Mark a notification sent only when this worker still owns its lease."""
    async with transactional(session):
        notification = await _get_leased_notification(
            session,
            notification_id=notification_id,
            worker_id=worker_id,
        )
        notification.status = NotificationStatus.SENT
        notification.sent_at = _now()
        notification.provider_message_id = provider_message_id[:255]
        notification.locked_at = None
        notification.locked_by = None
        notification.last_error_code = None
        await session.flush()


async def retry_or_fail_notification(
    session: AsyncSession,
    *,
    notification_id: UUID,
    worker_id: str,
    failure_code: str,
    policy: NotificationDeliveryPolicy,
    retryable: bool,
) -> None:
    """Release a failed notification for retry or terminally mark it failed."""
    async with transactional(session):
        notification = await _get_leased_notification(
            session,
            notification_id=notification_id,
            worker_id=worker_id,
        )
        now = _now()
        notification.locked_at = None
        notification.locked_by = None
        notification.last_error_code = failure_code

        if not retryable or notification.attempts >= policy.max_attempts:
            notification.status = NotificationStatus.FAILED
            notification.failed_at = now
        else:
            notification.status = NotificationStatus.PENDING
            notification.next_attempt_at = now + _retry_delay(
                notification.attempts,
                policy,
            )

        await session.flush()


def _render_message(notification: Notification, recipient_email: str) -> EmailMessage:
    """Render approved static copy without including workflow-sensitive values."""
    return render_notification_email(
        notification_id=notification.id,
        idempotency_key=notification.deduplication_key,
        recipient_email=recipient_email,
        event_type=notification.event_type,
        template_key=notification.template_key,
    )


async def process_pending_notifications(
    session: AsyncSession,
    *,
    worker_id: str,
    sender: EmailSender,
    policy: NotificationDeliveryPolicy = DEFAULT_NOTIFICATION_DELIVERY_POLICY,
) -> int:
    """Deliver one bounded batch of notification intents."""
    notifications = await claim_notifications(
        session,
        worker_id=worker_id,
        policy=policy,
        idempotency_retry_window=sender.idempotency_retry_window,
    )

    delivered = 0

    for notification in notifications:
        recipient_email = await session.scalar(
            select(User.email).where(
                User.id == notification.recipient_user_id,
                User.tenant_id == notification.tenant_id,
            )
        )
        if session.in_transaction():
            await session.commit()

        if recipient_email is None:
            await retry_or_fail_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
                failure_code="recipient_not_found",
                policy=policy,
                retryable=False,
            )
            continue

        try:
            message = _render_message(notification, recipient_email)
        except UnsupportedNotificationTemplateError:
            await retry_or_fail_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
                failure_code="unsupported_notification_template",
                policy=policy,
                retryable=False,
            )
            continue

        try:
            provider_message_id = await sender.send(message)
        except EmailDeliveryError as error:
            await retry_or_fail_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
                failure_code=error.code,
                policy=policy,
                retryable=error.retryable,
            )
            continue

        await mark_notification_sent(
            session,
            notification_id=notification.id,
            worker_id=worker_id,
            provider_message_id=provider_message_id,
        )
        delivered += 1

    return delivered
