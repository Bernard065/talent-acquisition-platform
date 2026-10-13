"""Unit tests for action-item digest cadence and idempotency decisions."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.notification import Notification, NotificationPreference
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationDigestFrequency,
    NotificationEventType,
    NotificationStatus,
)
from app.services import notification_action_item_digests as digest_service
from app.services.notification_action_item_digests import (
    _digest_key,
    _enabled_action_items,
    _preference,
    enqueue_action_item_digests,
)
from app.services.notification_action_items import NotificationActionItemRecord


def _action_item(
    *,
    kind: Literal["overdue_follow_up", "pending_interview_feedback"],
) -> NotificationActionItemRecord:
    """Create a minimal action item for cadence-filter tests."""
    application_id = uuid4()
    return NotificationActionItemRecord(
        id=f"{kind}:{uuid4()}",
        kind=kind,
        title="Review action item",
        candidate_name="Candidate",
        requisition_title="Role",
        due_at=datetime(2026, 10, 1, tzinfo=UTC),
        href=f"/dashboard/applications/{application_id}",
        application_id=application_id,
    )


def test_digest_preferences_default_to_enabled_daily() -> None:
    """Existing users without explicit digest preferences receive daily digests."""
    enabled, frequency = _preference(
        {},
        NotificationEventType.OVERDUE_FOLLOW_UP_DIGEST,
    )

    assert enabled is True
    assert frequency is NotificationDigestFrequency.DAILY


@pytest.mark.parametrize(
    ("frequency", "expected_kinds"),
    [
        (NotificationDigestFrequency.DAILY, ["overdue_follow_up"]),
        (NotificationDigestFrequency.WEEKLY, ["pending_interview_feedback"]),
    ],
)
def test_action_items_follow_individual_enabled_and_frequency_preferences(
    frequency: NotificationDigestFrequency,
    expected_kinds: list[str],
) -> None:
    """Each category obeys its own opt-in and selected delivery cadence."""
    items = [
        _action_item(kind="overdue_follow_up"),
        _action_item(kind="pending_interview_feedback"),
    ]
    preferences = {
        NotificationEventType.OVERDUE_FOLLOW_UP_DIGEST.value: (
            True,
            NotificationDigestFrequency.DAILY,
        ),
        NotificationEventType.PENDING_INTERVIEW_FEEDBACK_DIGEST.value: (
            frequency is NotificationDigestFrequency.WEEKLY,
            NotificationDigestFrequency.WEEKLY,
        ),
    }

    selected = _enabled_action_items(
        items,
        preferences=preferences,
        frequency=frequency,
    )

    assert [item.kind for item in selected] == expected_kinds


def test_digest_key_is_stable_and_scoped_to_recipient_cadence_and_period() -> None:
    """The same recipient and period deduplicate, while other periods do not."""
    user_id = uuid4()
    first = _digest_key(
        user_id=user_id,
        frequency=NotificationDigestFrequency.DAILY,
        period="2026-10-14",
    )

    assert first == _digest_key(
        user_id=user_id,
        frequency=NotificationDigestFrequency.DAILY,
        period="2026-10-14",
    )
    assert first != _digest_key(
        user_id=user_id,
        frequency=NotificationDigestFrequency.DAILY,
        period="2026-10-15",
    )
    assert first != _digest_key(
        user_id=user_id,
        frequency=NotificationDigestFrequency.WEEKLY,
        period="2026-10-14",
    )


async def _seed_recruiter(session: AsyncSession) -> User:
    """Create one recruiter eligible to receive a digest."""
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name=f"Digest Tenant {tenant_id.hex[:12]}",
        slug=f"digest-{tenant_id.hex[:12]}",
    )
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant_id,
        external_subject=f"digest-recruiter-{tenant_id.hex}",
        email=f"digest-{tenant_id.hex[:12]}@example.test",
        display_name="Digest Recruiter",
    )
    session.add(user)
    await session.flush()
    session.add(UserRoleAssignment(user_id=user.id, role=Role.RECRUITER))
    await session.flush()
    return user


@pytest_asyncio.fixture
async def digest_action_items() -> list[NotificationActionItemRecord]:
    """Return one item for each supported digest category."""
    return [
        _action_item(kind="overdue_follow_up"),
        _action_item(kind="pending_interview_feedback"),
    ]


@pytest.mark.asyncio
async def test_scheduler_defaults_to_daily_and_deduplicates_within_day(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    digest_action_items: list[NotificationActionItemRecord],
) -> None:
    """A user without saved preferences gets one daily digest per UTC day."""
    user = await _seed_recruiter(session)

    async def list_items(
        _session: AsyncSession,
        *,
        context: TenantContext,
    ) -> list[NotificationActionItemRecord]:
        assert context.subject == user.external_subject
        return digest_action_items

    monkeypatch.setattr(digest_service, "list_notification_action_items", list_items)
    first_count = await enqueue_action_item_digests(
        session,
        now=datetime(2026, 10, 14, 6, 0, tzinfo=UTC),
    )
    second_count = await enqueue_action_item_digests(
        session,
        now=datetime(2026, 10, 14, 8, 0, tzinfo=UTC),
    )

    notifications = list(
        await session.scalars(
            select(Notification).where(Notification.recipient_user_id == user.id)
        )
    )
    assert first_count == 1
    assert second_count == 0
    assert len(notifications) == 1
    assert notifications[0].event_type == "action_item.daily_digest"
    assert notifications[0].status is NotificationStatus.PENDING


@pytest.mark.asyncio
async def test_scheduler_respects_category_preferences_and_weekly_deduplication(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    digest_action_items: list[NotificationActionItemRecord],
) -> None:
    """Weekly cadence and disabled categories are honored across a week."""
    user = await _seed_recruiter(session)
    session.add_all(
        [
            NotificationPreference(
                tenant_id=user.tenant_id,
                user_id=user.id,
                event_type=NotificationEventType.OVERDUE_FOLLOW_UP_DIGEST.value,
                channel=NotificationChannel.EMAIL,
                enabled=False,
                digest_frequency=NotificationDigestFrequency.WEEKLY.value,
            ),
            NotificationPreference(
                tenant_id=user.tenant_id,
                user_id=user.id,
                event_type=(
                    NotificationEventType.PENDING_INTERVIEW_FEEDBACK_DIGEST.value
                ),
                channel=NotificationChannel.EMAIL,
                enabled=True,
                digest_frequency=NotificationDigestFrequency.WEEKLY.value,
            ),
        ]
    )
    await session.flush()

    async def list_items(
        _session: AsyncSession,
        *,
        context: TenantContext,
    ) -> list[NotificationActionItemRecord]:
        assert context.subject == user.external_subject
        return digest_action_items

    monkeypatch.setattr(digest_service, "list_notification_action_items", list_items)
    first_count = await enqueue_action_item_digests(
        session,
        now=datetime(2026, 10, 14, 6, 0, tzinfo=UTC),
    )
    second_count = await enqueue_action_item_digests(
        session,
        now=datetime(2026, 10, 15, 6, 0, tzinfo=UTC),
    )
    notifications = list(
        await session.scalars(
            select(Notification).where(Notification.recipient_user_id == user.id)
        )
    )

    assert first_count == 1
    assert second_count == 0
    assert len(notifications) == 1
    assert notifications[0].event_type == "action_item.weekly_digest"
