"""Outbox-driven, deduplicated creation of notification delivery intents."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidate import Candidate
from app.db.models.identity import User
from app.db.models.notification import Notification, NotificationPreference
from app.db.models.outbox import OutboxEvent
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationEventType,
    NotificationStatus,
)
from app.services.notification_email_templates import (
    resolve_notification_email_template,
)
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
)

_NOTIFICATION_REQUESTED_EVENT = "notification.requested"


@dataclass(frozen=True, slots=True)
class NotificationIntentWorkerResult:
    """Outcome of one bounded notification-intent worker cycle."""

    claimed: int
    processed: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    """Validated, non-sensitive notification request payload."""

    recipient_user_id: UUID | None
    recipient_candidate_id: UUID | None
    channel: NotificationChannel
    event_type: NotificationEventType
    entity_type: str
    entity_id: UUID
    template_key: str
    deduplication_key: str
    event_version: int | None
    scheduled_at: datetime | None


def _now() -> datetime:
    return datetime.now(UTC)


def _request_from_event(event: OutboxEvent) -> NotificationRequest:
    """Parse the strictly controlled notification request payload."""
    payload = event.payload

    recipient_user_id = (
        UUID(str(payload["recipient_user_id"]))
        if payload.get("recipient_user_id") is not None
        else None
    )
    recipient_candidate_id = (
        UUID(str(payload["recipient_candidate_id"]))
        if payload.get("recipient_candidate_id") is not None
        else None
    )
    channel = NotificationChannel(str(payload["channel"]))
    event_type = NotificationEventType(str(payload["notification_event_type"]))
    entity_type = str(payload["entity_type"]).strip()
    entity_id = UUID(str(payload["entity_id"]))
    template_key = str(payload["template_key"]).strip()
    deduplication_key = str(payload["notification_deduplication_key"]).strip()
    occurrence_key = payload.get("occurrence_key")
    event_version = int(str(occurrence_key)) if occurrence_key is not None else None
    scheduled_at_value = payload.get("scheduled_at")
    scheduled_at = (
        datetime.fromisoformat(str(scheduled_at_value).replace("Z", "+00:00"))
        if scheduled_at_value is not None
        else None
    )
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        raise ValueError("Notification schedule time must include a timezone.")

    if not entity_type or not template_key:
        raise ValueError("Notification entity type and template key are required.")
    if (recipient_user_id is None) == (recipient_candidate_id is None):
        raise ValueError("Exactly one notification recipient must be provided.")
    if recipient_candidate_id is not None and (
        event_type
        not in {
            NotificationEventType.INTERVIEW_SCHEDULED,
            NotificationEventType.INTERVIEW_RESCHEDULED,
            NotificationEventType.INTERVIEW_CANCELLED,
            NotificationEventType.INTERVIEW_REMINDER,
        }
        or entity_type != "interview_session"
    ):
        raise ValueError("Candidate recipients are supported only for interviews.")
    if event_version is not None and event_version < 1:
        raise ValueError("Notification occurrence version must be positive.")

    resolve_notification_email_template(
        event_type=event_type,
        template_key=template_key,
    )

    if len(deduplication_key) != 64:
        raise ValueError("Notification deduplication key must be a SHA-256 digest.")

    return NotificationRequest(
        recipient_user_id=recipient_user_id,
        recipient_candidate_id=recipient_candidate_id,
        channel=channel,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        template_key=template_key,
        deduplication_key=deduplication_key,
        event_version=event_version,
        scheduled_at=scheduled_at,
    )


async def create_notification_intent(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    request: NotificationRequest,
) -> Notification:
    """Create one durable intent, respecting tenant preferences and deduplication."""
    if request.recipient_user_id is not None:
        recipient = await session.scalar(
            select(User).where(
                User.id == request.recipient_user_id,
                User.tenant_id == event.tenant_id,
            )
        )
        if recipient is None:
            raise LookupError("Notification recipient was not found in this tenant.")

        preference = await session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == event.tenant_id,
                NotificationPreference.user_id == request.recipient_user_id,
                NotificationPreference.event_type == request.event_type.value,
                NotificationPreference.channel == request.channel,
            )
        )
    else:
        candidate = await session.scalar(
            select(Candidate.id).where(
                Candidate.id == request.recipient_candidate_id,
                Candidate.tenant_id == event.tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
        )
        if candidate is None:
            raise LookupError("Notification candidate was not found in this tenant.")
        preference = None

    enabled = preference is None or preference.enabled
    delivery_at = request.scheduled_at or _now()
    notification = Notification(
        tenant_id=event.tenant_id,
        recipient_user_id=request.recipient_user_id,
        recipient_candidate_id=request.recipient_candidate_id,
        channel=request.channel,
        status=NotificationStatus.PENDING if enabled else NotificationStatus.CANCELLED,
        event_type=request.event_type.value,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        template_key=request.template_key,
        deduplication_key=request.deduplication_key,
        event_version=request.event_version,
        scheduled_at=delivery_at,
        next_attempt_at=delivery_at,
        cancelled_at=None if enabled else _now(),
    )

    try:
        async with session.begin_nested():
            session.add(notification)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(Notification).where(
                Notification.tenant_id == event.tenant_id,
                Notification.recipient_user_id == request.recipient_user_id,
                Notification.recipient_candidate_id == request.recipient_candidate_id,
                Notification.channel == request.channel,
                Notification.event_type == request.event_type.value,
                Notification.deduplication_key == request.deduplication_key,
            )
        )
        if existing is None:
            raise
        return existing

    return notification


async def process_notification_request_events(
    session: AsyncSession,
    *,
    worker_id: str,
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> NotificationIntentWorkerResult:
    """Claim notification requests and turn them into durable delivery intents."""
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({_NOTIFICATION_REQUESTED_EVENT}),
    )

    processed = 0
    dead_lettered = 0

    for event in events:
        try:
            request = _request_from_event(event)
            await create_notification_intent(session, event=event, request=request)
        except (KeyError, TypeError, ValueError):
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="invalid_notification_event_payload",
            )
            dead_lettered += 1
            continue
        except LookupError:
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="notification_recipient_not_found",
            )
            dead_lettered += 1
            continue

        await mark_outbox_event_processed(
            session,
            event_id=event.id,
            worker_id=worker_id,
        )
        processed += 1

    return NotificationIntentWorkerResult(
        claimed=len(events),
        processed=processed,
        dead_lettered=dead_lettered,
    )
