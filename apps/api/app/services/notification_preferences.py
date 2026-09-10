"""Tenant-scoped self-service notification preference operations."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.identity import User
from app.db.models.notification import NotificationPreference
from app.db.transactions import transactional
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationEventType,
)
from app.services.audit import record_audit_event
from app.services.notification_preference_errors import (
    NotificationPreferenceAccessDeniedError,
    NotificationPreferenceVersionConflictError,
)


@dataclass(frozen=True, slots=True)
class NotificationPreferenceView:
    """One effective preference, including the default when not persisted."""

    event_type: NotificationEventType
    channel: NotificationChannel
    enabled: bool
    version: int
    updated_at: datetime | None


async def _load_current_user(
    session: AsyncSession,
    *,
    context: TenantContext,
    lock: bool = False,
) -> User:
    """Resolve the verified subject to its tenant-owned internal user record."""
    statement = select(User).where(
        User.tenant_id == context.tenant_id,
        User.external_subject == context.subject,
    )

    if lock:
        statement = statement.with_for_update()

    user = await session.scalar(statement)
    if user is None:
        raise NotificationPreferenceAccessDeniedError(
            "The caller does not have an internal tenant user identity."
        )

    return user


def _view(
    *,
    event_type: NotificationEventType,
    channel: NotificationChannel,
    preference: NotificationPreference | None,
) -> NotificationPreferenceView:
    """Return persisted state or the enabled-by-default effective state."""
    if preference is None:
        return NotificationPreferenceView(
            event_type=event_type,
            channel=channel,
            enabled=True,
            version=0,
            updated_at=None,
        )

    return NotificationPreferenceView(
        event_type=event_type,
        channel=channel,
        enabled=preference.enabled,
        version=preference.version,
        updated_at=preference.updated_at,
    )


async def list_notification_preferences(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> tuple[NotificationPreferenceView, ...]:
    """List every supported effective preference for the authenticated user."""
    user = await _load_current_user(session, context=context)

    preferences = list(
        await session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == context.tenant_id,
                NotificationPreference.user_id == user.id,
            )
        )
    )
    stored = {
        (preference.event_type, preference.channel): preference
        for preference in preferences
    }

    return tuple(
        _view(
            event_type=event_type,
            channel=channel,
            preference=stored.get((event_type.value, channel)),
        )
        for event_type in NotificationEventType
        for channel in NotificationChannel
    )


async def update_notification_preference(
    session: AsyncSession,
    *,
    context: TenantContext,
    event_type: NotificationEventType,
    channel: NotificationChannel,
    enabled: bool,
    expected_version: int,
) -> NotificationPreferenceView:
    """
    Create or update the caller's own preference with optimistic concurrency.

    Version zero represents the implicit default where no preference exists.
    Locking the user row serializes concurrent first-time preference creation.
    """
    async with transactional(session):
        user = await _load_current_user(
            session,
            context=context,
            lock=True,
        )
        preference = await session.scalar(
            select(NotificationPreference)
            .where(
                NotificationPreference.tenant_id == context.tenant_id,
                NotificationPreference.user_id == user.id,
                NotificationPreference.event_type == event_type.value,
                NotificationPreference.channel == channel,
            )
            .with_for_update()
        )

        actual_version = preference.version if preference is not None else 0
        if actual_version != expected_version:
            raise NotificationPreferenceVersionConflictError(
                "Notification preference has changed; retrieve it and retry."
            )

        if preference is None:
            preference = NotificationPreference(
                tenant_id=context.tenant_id,
                user_id=user.id,
                event_type=event_type.value,
                channel=channel,
                enabled=enabled,
            )
            session.add(preference)
            await session.flush()
        elif preference.enabled != enabled:
            preference.enabled = enabled
            await session.flush()

        record_audit_event(
            session,
            context=context,
            action="notification_preference.updated",
            entity_type="notification_preference",
            entity_id=str(preference.id),
            details={
                "event_type": event_type.value,
                "channel": channel.value,
                "enabled": preference.enabled,
                "version": preference.version,
            },
        )
        await session.flush()
        await session.refresh(preference)

    return _view(
        event_type=event_type,
        channel=channel,
        preference=preference,
    )
