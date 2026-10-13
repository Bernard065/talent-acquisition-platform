"""Leased, idempotent delivery of transactional email notification intents."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import User, UserRoleAssignment
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.job_posting import JobPosting
from app.db.models.notification import Notification, NotificationPreference
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.interviews.enums import (
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.job_postings.enums import JobPostingStatus
from app.domains.notifications.enums import (
    NotificationDigestFrequency,
    NotificationEventType,
    NotificationStatus,
)
from app.services.email_sender import EmailDeliveryError, EmailMessage, EmailSender
from app.services.notification_action_items import (
    NotificationActionItemRecord,
    list_notification_action_items,
)
from app.services.notification_email_templates import (
    InterviewNotificationDetails,
    UnsupportedNotificationTemplateError,
    render_action_item_digest_email,
    render_interview_notification_email,
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


class StaleInterviewNotificationError(Exception):
    """An interview change superseded a notification before delivery."""


class StaleActionItemDigestError(Exception):
    """A daily digest no longer contains any enabled action items."""


_ACTION_ITEM_DIGEST_FREQUENCIES = {
    "action_item.daily_digest": NotificationDigestFrequency.DAILY,
    "action_item.weekly_digest": NotificationDigestFrequency.WEEKLY,
}
_OVERDUE_FOLLOW_UP_DIGEST = NotificationEventType.OVERDUE_FOLLOW_UP_DIGEST
_PENDING_FEEDBACK_DIGEST = (
    NotificationEventType.PENDING_INTERVIEW_FEEDBACK_DIGEST
)


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


async def cancel_stale_notification(
    session: AsyncSession,
    *,
    notification_id: UUID,
    worker_id: str,
    failure_code: str = "interview_event_superseded",
) -> None:
    """Cancel a leased message whose interview state has since changed."""
    async with transactional(session):
        notification = await _get_leased_notification(
            session,
            notification_id=notification_id,
            worker_id=worker_id,
        )
        notification.status = NotificationStatus.CANCELLED
        notification.cancelled_at = _now()
        notification.locked_at = None
        notification.locked_by = None
        notification.last_error_code = failure_code
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


async def _recipient_email(
    session: AsyncSession,
    notification: Notification,
) -> str | None:
    """Resolve an internal or candidate email at delivery time."""
    if notification.recipient_user_id is not None:
        return cast(
            str | None,
            await session.scalar(
                select(User.email).where(
                    User.id == notification.recipient_user_id,
                    User.tenant_id == notification.tenant_id,
                )
            )
        )

    if notification.recipient_candidate_id is not None:
        return cast(
            str | None,
            await session.scalar(
                select(Candidate.email).where(
                    Candidate.id == notification.recipient_candidate_id,
                    Candidate.tenant_id == notification.tenant_id,
                    Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
                )
            )
        )

    return None


async def _interview_notification_details(
    session: AsyncSession,
    *,
    notification: Notification,
    web_app_base_url: str,
) -> InterviewNotificationDetails | None:
    """Resolve current interview data and verify the notification recipient."""
    if notification.entity_type != "interview_session":
        return None

    public_job_id = (
        select(JobPosting.public_id)
        .where(
            JobPosting.requisition_id == Requisition.id,
            JobPosting.tenant_id == Requisition.tenant_id,
            JobPosting.status == JobPostingStatus.PUBLISHED,
        )
        .order_by(JobPosting.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    row = await session.execute(
        select(
            InterviewSession,
            Application.candidate_id,
            Requisition.title,
            public_job_id,
        )
        .join(
            Application,
            and_(
                Application.id == InterviewSession.application_id,
                Application.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .join(
            Requisition,
            and_(
                Requisition.id == Application.requisition_id,
                Requisition.tenant_id == Application.tenant_id,
            ),
        )
        .where(
            InterviewSession.id == notification.entity_id,
            InterviewSession.tenant_id == notification.tenant_id,
        )
        .limit(1)
    )
    resolved = row.first()
    if resolved is None:
        return None

    interview, candidate_id, role_title, public_job_id = resolved
    try:
        notification_event_type = NotificationEventType(notification.event_type)
    except ValueError:
        return None
    is_current_event = (
        notification.event_version is None
        or notification.event_version == interview.version
    )
    if notification_event_type in {
        NotificationEventType.INTERVIEW_SCHEDULED,
        NotificationEventType.INTERVIEW_RESCHEDULED,
        NotificationEventType.INTERVIEW_REMINDER,
    } and (
        interview.status is not InterviewSessionStatus.SCHEDULED or not is_current_event
    ):
        raise StaleInterviewNotificationError
    if (
        notification_event_type is NotificationEventType.INTERVIEW_REMINDER
        and interview.scheduled_start_at <= _now()
    ):
        raise StaleInterviewNotificationError
    if notification_event_type is NotificationEventType.INTERVIEW_CANCELLED and (
        interview.status is not InterviewSessionStatus.CANCELLED or not is_current_event
    ):
        raise StaleInterviewNotificationError

    is_candidate = notification.recipient_candidate_id is not None
    if is_candidate:
        if notification.recipient_candidate_id != candidate_id:
            return None
    elif notification.recipient_user_id is not None:
        assigned = await session.scalar(
            select(InterviewParticipant.id).where(
                InterviewParticipant.tenant_id == notification.tenant_id,
                InterviewParticipant.interview_session_id == interview.id,
                InterviewParticipant.user_id == notification.recipient_user_id,
                InterviewParticipant.role == InterviewParticipantRole.INTERVIEWER,
            )
        )
        if assigned is None:
            return None
    else:
        return None

    base_url = web_app_base_url.rstrip("/")
    role_url = (
        f"{base_url}/careers/{public_job_id}" if public_job_id is not None else None
    )
    return InterviewNotificationDetails(
        role_title=role_title,
        scheduled_start_at=interview.scheduled_start_at,
        scheduled_end_at=interview.scheduled_end_at,
        interview_format=(
            interview.format.value.replace("_", " ").title()
            if interview.format is not None
            else None
        ),
        location=interview.location,
        meeting_url=interview.meeting_url,
        interview_url=f"{base_url}/dashboard/interviews/{interview.id}",
        role_url=role_url,
        is_candidate=is_candidate,
    )


async def _render_delivery_message(
    session: AsyncSession,
    *,
    notification: Notification,
    recipient_email: str,
    web_app_base_url: str,
) -> EmailMessage:
    """Render static notices or authorized, current interview schedule details."""
    if notification.event_type in _ACTION_ITEM_DIGEST_FREQUENCIES:
        return await _render_action_item_digest(
            session,
            notification=notification,
            recipient_email=recipient_email,
            web_app_base_url=web_app_base_url,
        )

    try:
        event_type = NotificationEventType(notification.event_type)
    except ValueError:
        return _render_message(notification, recipient_email)

    if event_type not in {
        NotificationEventType.INTERVIEW_SCHEDULED,
        NotificationEventType.INTERVIEW_RESCHEDULED,
        NotificationEventType.INTERVIEW_CANCELLED,
        NotificationEventType.INTERVIEW_REMINDER,
    }:
        return _render_message(notification, recipient_email)

    details = await _interview_notification_details(
        session,
        notification=notification,
        web_app_base_url=web_app_base_url,
    )
    if details is None:
        raise UnsupportedNotificationTemplateError(
            "Interview notification recipient or session is no longer available."
        )

    return render_interview_notification_email(
        notification_id=notification.id,
        idempotency_key=notification.deduplication_key,
        recipient_email=recipient_email,
        event_type=notification.event_type,
        template_key=notification.template_key,
        details=details,
    )


async def _render_action_item_digest(
    session: AsyncSession,
    *,
    notification: Notification,
    recipient_email: str,
    web_app_base_url: str,
) -> EmailMessage:
    """Re-resolve the recipient's enabled items immediately before delivery."""
    user_id = notification.recipient_user_id
    if (
        notification.entity_type != "action_item_digest"
        or user_id is None
        or notification.entity_id != user_id
    ):
        raise UnsupportedNotificationTemplateError(
            "Daily action digest recipient is invalid."
        )

    user = await session.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == notification.tenant_id,
        )
    )
    if user is None:
        raise UnsupportedNotificationTemplateError(
            "Daily action digest recipient is unavailable."
        )

    preference_rows = await session.execute(
        select(
            NotificationPreference.event_type,
            NotificationPreference.enabled,
            NotificationPreference.digest_frequency,
        ).where(
            NotificationPreference.tenant_id == notification.tenant_id,
            NotificationPreference.user_id == user_id,
            NotificationPreference.channel == notification.channel,
            NotificationPreference.event_type.in_(
                [
                    _OVERDUE_FOLLOW_UP_DIGEST.value,
                    _PENDING_FEEDBACK_DIGEST.value,
                ]
            ),
        )
    )
    enabled_preferences: dict[
        str, tuple[bool, NotificationDigestFrequency]
    ] = {
        event_type: (enabled, NotificationDigestFrequency(frequency))
        for event_type, enabled, frequency in preference_rows.all()
    }
    digest_frequency = _ACTION_ITEM_DIGEST_FREQUENCIES[notification.event_type]
    if not any(
        enabled_preferences.get(
            event_type.value,
            (True, NotificationDigestFrequency.DAILY),
        )[0]
        and enabled_preferences.get(
            event_type.value,
            (True, NotificationDigestFrequency.DAILY),
        )[1]
        is digest_frequency
        for event_type in (_OVERDUE_FOLLOW_UP_DIGEST, _PENDING_FEEDBACK_DIGEST)
    ):
        raise StaleActionItemDigestError

    role_rows = await session.scalars(
        select(UserRoleAssignment.role).where(
            UserRoleAssignment.user_id == user_id,
        )
    )
    context = TenantContext(
        tenant_id=notification.tenant_id,
        subject=user.external_subject,
        roles=frozenset(role_rows),
        request_id="notification-digest-delivery",
    )
    items = await list_notification_action_items(session, context=context)
    enabled_items: list[NotificationActionItemRecord] = [
        item
        for item in items
        if (
            enabled_preferences.get(
                (
                    _OVERDUE_FOLLOW_UP_DIGEST.value
                    if item.kind == "overdue_follow_up"
                    else _PENDING_FEEDBACK_DIGEST.value
                ),
                (True, NotificationDigestFrequency.DAILY),
            )[0]
            and enabled_preferences.get(
                (
                    _OVERDUE_FOLLOW_UP_DIGEST.value
                    if item.kind == "overdue_follow_up"
                    else _PENDING_FEEDBACK_DIGEST.value
                ),
                (True, NotificationDigestFrequency.DAILY),
            )[1]
            is digest_frequency
        )
    ]
    overdue_count = sum(item.kind == "overdue_follow_up" for item in enabled_items)
    feedback_count = sum(
        item.kind == "pending_interview_feedback" for item in enabled_items
    )
    if overdue_count + feedback_count == 0:
        raise StaleActionItemDigestError

    return render_action_item_digest_email(
        notification_id=notification.id,
        idempotency_key=notification.deduplication_key,
        recipient_email=recipient_email,
        overdue_follow_up_count=overdue_count,
        pending_feedback_count=feedback_count,
        frequency=digest_frequency,
        web_app_base_url=web_app_base_url,
    )


async def process_pending_notifications(
    session: AsyncSession,
    *,
    worker_id: str,
    sender: EmailSender,
    policy: NotificationDeliveryPolicy = DEFAULT_NOTIFICATION_DELIVERY_POLICY,
    web_app_base_url: str = "http://localhost:3000",
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
        recipient_email = await _recipient_email(session, notification)
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
            message = await _render_delivery_message(
                session,
                notification=notification,
                recipient_email=recipient_email,
                web_app_base_url=web_app_base_url,
            )
            if session.in_transaction():
                await session.commit()
        except UnsupportedNotificationTemplateError:
            if session.in_transaction():
                await session.commit()
            await retry_or_fail_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
                failure_code="unsupported_notification_template",
                policy=policy,
                retryable=False,
            )
            continue
        except StaleInterviewNotificationError:
            if session.in_transaction():
                await session.commit()
            await cancel_stale_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
            )
            continue
        except StaleActionItemDigestError:
            if session.in_transaction():
                await session.commit()
            await cancel_stale_notification(
                session,
                notification_id=notification.id,
                worker_id=worker_id,
                failure_code="action_item_digest_no_longer_needed",
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
