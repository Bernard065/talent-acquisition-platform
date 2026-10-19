"""Create deduplicated daily and weekly recruiter action-item digests."""

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import User, UserRoleAssignment
from app.db.models.notification import Notification, NotificationPreference
from app.db.transactions import transactional
from app.domains.notifications.action_item_digest_policy import (
    ACTION_ITEM_DIGEST_PREFERENCE_BY_KIND,
    ACTION_ITEM_DIGEST_PREFERENCES,
)
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationDigestFrequency,
    NotificationEventType,
    NotificationStatus,
)
from app.services.notification_action_items import (
    NotificationActionItemRecord,
    list_notification_action_items,
)

_DAILY_DIGEST_EVENT = "action_item.daily_digest"
_WEEKLY_DIGEST_EVENT = "action_item.weekly_digest"
_DIGEST_PREFERENCES = ACTION_ITEM_DIGEST_PREFERENCES
_DIGEST_ENTITY_TYPE = "action_item_digest"
_DIGEST_TEMPLATE_KEY = "action_item_digest"


def _digest_key(
    *,
    user_id: UUID,
    frequency: NotificationDigestFrequency,
    period: str,
) -> str:
    """Return a stable, non-sensitive idempotency digest per user and period."""
    identity = f"action-item-digest:{frequency.value}:{user_id}:{period}"
    return sha256(identity.encode("utf-8")).hexdigest()


def _preference(
    preferences: dict[str, tuple[bool, NotificationDigestFrequency]],
    event_type: NotificationEventType,
) -> tuple[bool, NotificationDigestFrequency]:
    """Use daily, enabled delivery as the default for an unset preference."""
    return preferences.get(
        event_type.value,
        (True, NotificationDigestFrequency.DAILY),
    )


def _enabled_action_items(
    items: list[NotificationActionItemRecord],
    *,
    preferences: dict[str, tuple[bool, NotificationDigestFrequency]],
    frequency: NotificationDigestFrequency,
) -> list[NotificationActionItemRecord]:
    """Keep items enabled for this recipient and this digest cadence."""
    enabled_items: list[NotificationActionItemRecord] = []
    for item in items:
        event_type = ACTION_ITEM_DIGEST_PREFERENCE_BY_KIND.get(item.kind)
        if event_type is None:
            continue
        enabled, item_frequency = _preference(preferences, event_type)
        if enabled and item_frequency is frequency:
            enabled_items.append(item)
    return enabled_items


async def enqueue_action_item_digests(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """Persist due digest intents; delivery rechecks items and preferences.

    A weekly digest is queued on the first worker cycle of the ISO week after
    the configured delivery hour, and only when the user has eligible items.
    """
    created_at = now or datetime.now(UTC)
    if created_at.tzinfo is None:
        raise ValueError("Digest scheduling time must include a UTC offset.")
    created_at = created_at.astimezone(UTC)

    current_day = created_at.date()
    day_start = datetime.combine(current_day, time.min, tzinfo=UTC)
    next_day = day_start + timedelta(days=1)
    week_start = day_start - timedelta(days=current_day.weekday())
    next_week = week_start + timedelta(days=7)
    iso_calendar = current_day.isocalendar()
    daily_period = current_day.isoformat()
    weekly_period = f"{iso_calendar.year}-W{iso_calendar.week:02d}"

    async with transactional(session):
        users = list(
            await session.scalars(
                select(User)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .distinct()
                .order_by(User.tenant_id, User.id)
            )
        )
        if not users:
            return 0

        user_ids = [user.id for user in users]
        role_rows = await session.execute(
            select(UserRoleAssignment.user_id, UserRoleAssignment.role).where(
                UserRoleAssignment.user_id.in_(user_ids)
            )
        )
        roles_by_user: dict[UUID, set[Role]] = defaultdict(set)
        for user_id, role in role_rows.all():
            roles_by_user[user_id].add(role)

        preference_rows = await session.execute(
            select(
                NotificationPreference.user_id,
                NotificationPreference.event_type,
                NotificationPreference.enabled,
                NotificationPreference.digest_frequency,
            ).where(
                NotificationPreference.user_id.in_(user_ids),
                NotificationPreference.event_type.in_(
                    [preference.value for preference in _DIGEST_PREFERENCES]
                ),
                NotificationPreference.channel == NotificationChannel.EMAIL,
            )
        )
        preferences_by_user: dict[
            UUID, dict[str, tuple[bool, NotificationDigestFrequency]]
        ] = defaultdict(dict)
        for user_id, event_type, enabled, frequency in preference_rows.all():
            preferences_by_user[user_id][event_type] = (
                enabled,
                NotificationDigestFrequency(frequency),
            )

        already_enqueued: set[tuple[UUID, NotificationDigestFrequency]] = set()
        existing_rows = await session.execute(
            select(
                Notification.entity_id,
                Notification.event_type,
                Notification.scheduled_at,
            ).where(
                Notification.event_type.in_(
                    [_DAILY_DIGEST_EVENT, _WEEKLY_DIGEST_EVENT]
                ),
                Notification.entity_type == _DIGEST_ENTITY_TYPE,
                Notification.scheduled_at >= week_start,
                Notification.scheduled_at < next_week,
                Notification.recipient_user_id.in_(user_ids),
            )
        )
        for entity_id, event_type, scheduled_at in existing_rows.all():
            frequency = (
                NotificationDigestFrequency.DAILY
                if event_type == _DAILY_DIGEST_EVENT
                else NotificationDigestFrequency.WEEKLY
            )
            if (
                frequency is NotificationDigestFrequency.DAILY
                and scheduled_at >= day_start
                and scheduled_at < next_day
            ) or frequency is NotificationDigestFrequency.WEEKLY:
                already_enqueued.add((entity_id, frequency))

        digest_rows: list[dict[str, object]] = []
        for user in users:
            user_preferences = preferences_by_user[user.id]
            if not any(
                _preference(user_preferences, event_type)[0]
                for event_type in _DIGEST_PREFERENCES
            ):
                continue

            context = TenantContext(
                tenant_id=user.tenant_id,
                subject=user.external_subject,
                roles=frozenset(roles_by_user[user.id]),
                request_id="notification-digest-worker",
            )
            items = await list_notification_action_items(session, context=context)

            for frequency, event_type, period in (
                (
                    NotificationDigestFrequency.DAILY,
                    _DAILY_DIGEST_EVENT,
                    daily_period,
                ),
                (
                    NotificationDigestFrequency.WEEKLY,
                    _WEEKLY_DIGEST_EVENT,
                    weekly_period,
                ),
            ):
                if (user.id, frequency) in already_enqueued:
                    continue
                eligible_items = _enabled_action_items(
                    items,
                    preferences=user_preferences,
                    frequency=frequency,
                )
                if not eligible_items:
                    continue

                digest_rows.append(
                    {
                        "tenant_id": user.tenant_id,
                        "recipient_user_id": user.id,
                        "recipient_candidate_id": None,
                        "channel": NotificationChannel.EMAIL,
                        "status": NotificationStatus.PENDING,
                        "event_type": event_type,
                        "entity_type": _DIGEST_ENTITY_TYPE,
                        "entity_id": user.id,
                        "template_key": _DIGEST_TEMPLATE_KEY,
                        "deduplication_key": _digest_key(
                            user_id=user.id,
                            frequency=frequency,
                            period=period,
                        ),
                        "event_version": None,
                        "scheduled_at": created_at,
                        "next_attempt_at": created_at,
                    }
                )

        if not digest_rows:
            return 0

        result = await session.execute(
            pg_insert(Notification)
            .values(digest_rows)
            .on_conflict_do_nothing(
                constraint="uq_notifications_tenant_recipient_event_deduplication"
            )
            .returning(Notification.id)
        )
        return len(result.scalars().all())
