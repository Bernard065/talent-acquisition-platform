"""PostgreSQL integration tests for retry-safe notification delivery."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.db.models.identity import Tenant, User
from app.db.models.notification import Notification
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.services.email_sender import EmailDeliveryError, EmailMessage
from app.services.notification_delivery import (
    NotificationDeliveryPolicy,
    claim_notifications,
    process_pending_notifications,
    retry_or_fail_notification,
)


class FakeEmailSender:
    """Controllable sender that records messages without external delivery."""

    idempotency_retry_window: timedelta | None = None

    def __init__(self, error: EmailDeliveryError | None = None) -> None:
        self.error = error
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> str:
        """Record a dispatched email and optionally simulate a delivery failure."""
        self.messages.append(message)

        if self.error is not None:
            raise self.error

        return f"provider:{message.idempotency_key}"


@pytest_asyncio.fixture(name="notification_session_factory")
async def notification_session_factory_fixture(
    database_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide independent sessions for concurrent lease tests."""
    factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    yield factory

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )


async def _seed_notification(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    status: NotificationStatus = NotificationStatus.PENDING,
    attempts: int = 0,
    locked_at: datetime | None = None,
    locked_by: str | None = None,
    first_delivery_attempt_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    """Create a delivery-ready internal email notification."""
    tenant_id = uuid4()
    notification_id = uuid4()

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Delivery Tenant {tenant_id.hex[:12]}",
                slug=f"delivery-{tenant_id.hex[:12]}",
            )
        )
        await session.flush()

        recipient = User(
            tenant_id=tenant_id,
            external_subject=f"delivery-recipient-{tenant_id.hex}",
            email=f"delivery-{tenant_id.hex[:10]}@example.test",
            display_name="Delivery Recipient",
        )
        session.add(recipient)
        await session.flush()

        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                recipient_user_id=recipient.id,
                channel=NotificationChannel.EMAIL,
                status=status,
                event_type="offer.sent",
                entity_type="offer",
                entity_id=uuid4(),
                template_key="offer_sent",
                deduplication_key=uuid4().hex + uuid4().hex,
                attempts=attempts,
                locked_at=locked_at,
                locked_by=locked_by,
                first_delivery_attempt_at=first_delivery_attempt_at,
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
                sent_at=datetime.now(UTC)
                if status is NotificationStatus.SENT
                else None,
                failed_at=datetime.now(UTC)
                if status is NotificationStatus.FAILED
                else None,
            )
        )

    return tenant_id, notification_id


async def _get_notification(
    session_factory: async_sessionmaker[AsyncSession],
    notification_id: UUID,
) -> Notification:
    async with session_factory() as session:
        notification = await session.get(Notification, notification_id)
        assert notification is not None
        return notification


@pytest.mark.asyncio
async def test_concurrent_workers_claim_only_one_notification(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Row locks ensure only one worker owns a due notification."""
    _, notification_id = await _seed_notification(notification_session_factory)

    async with notification_session_factory() as first_session:
        async with notification_session_factory() as second_session:
            first, second = await __import__("asyncio").gather(
                claim_notifications(first_session, worker_id="worker-one"),
                claim_notifications(second_session, worker_id="worker-two"),
            )

    claimed_ids = [item.id for item in [*first, *second]]

    assert claimed_ids == [notification_id]


@pytest.mark.asyncio
async def test_recovers_stale_lease_and_reclaims_notification(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A crashed sender lease is retried by another worker."""
    _, notification_id = await _seed_notification(
        notification_session_factory,
        status=NotificationStatus.SENDING,
        attempts=1,
        locked_at=datetime.now(UTC) - timedelta(minutes=10),
        locked_by="crashed-worker",
    )
    policy = NotificationDeliveryPolicy(
        batch_size=1,
        max_attempts=3,
        visibility_timeout=timedelta(minutes=1),
    )

    async with notification_session_factory() as session:
        claimed = await claim_notifications(
            session,
            worker_id="recovery-worker",
            policy=policy,
        )

    notification = await _get_notification(
        notification_session_factory,
        notification_id,
    )

    assert [item.id for item in claimed] == [notification_id]
    assert notification.status is NotificationStatus.SENDING
    assert notification.locked_by == "recovery-worker"
    assert notification.attempts == 2
    assert notification.last_error_code == "lease_expired"


@pytest.mark.asyncio
async def test_does_not_retry_after_provider_idempotency_window_expires(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ambiguous sends are not repeated after the provider forgets the key."""
    _, notification_id = await _seed_notification(
        notification_session_factory,
        attempts=1,
        first_delivery_attempt_at=datetime.now(UTC) - timedelta(hours=24),
    )

    async with notification_session_factory() as session:
        claimed = await claim_notifications(
            session,
            worker_id="worker-recovery",
            idempotency_retry_window=timedelta(hours=23),
        )

    notification = await _get_notification(
        notification_session_factory,
        notification_id,
    )

    assert claimed == []
    assert notification.status is NotificationStatus.FAILED
    assert notification.failed_at is not None
    assert notification.locked_at is None
    assert notification.locked_by is None
    assert notification.last_error_code == "provider_idempotency_window_expired"


@pytest.mark.asyncio
async def test_retries_with_exponential_backoff(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Temporary provider failures use bounded exponential retry delays."""
    _, notification_id = await _seed_notification(notification_session_factory)
    policy = NotificationDeliveryPolicy(
        batch_size=1,
        max_attempts=3,
        base_retry_delay=timedelta(seconds=10),
        maximum_retry_delay=timedelta(seconds=60),
    )

    async with notification_session_factory() as session:
        claimed = await claim_notifications(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        started = datetime.now(UTC)

        await retry_or_fail_notification(
            session,
            notification_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="email_provider_unavailable",
            policy=policy,
            retryable=True,
        )

    notification = await _get_notification(
        notification_session_factory,
        notification_id,
    )

    assert notification.status is NotificationStatus.PENDING
    assert notification.attempts == 1
    assert notification.last_error_code == "email_provider_unavailable"
    assert notification.next_attempt_at >= started + timedelta(seconds=10)


@pytest.mark.asyncio
async def test_marks_terminal_delivery_failure_after_max_attempts(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Retries stop once the maximum attempt budget is exhausted."""
    _, notification_id = await _seed_notification(notification_session_factory)
    policy = NotificationDeliveryPolicy(batch_size=1, max_attempts=1)

    async with notification_session_factory() as session:
        claimed = await claim_notifications(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        await retry_or_fail_notification(
            session,
            notification_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="email_provider_unavailable",
            policy=policy,
            retryable=True,
        )

    notification = await _get_notification(
        notification_session_factory,
        notification_id,
    )

    assert notification.status is NotificationStatus.FAILED
    assert notification.failed_at is not None
    assert notification.attempts == 1


@pytest.mark.asyncio
async def test_delivers_pending_notification_once(
    notification_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A successful provider response marks the leased intent as sent."""
    _, notification_id = await _seed_notification(notification_session_factory)
    sender = FakeEmailSender()

    async with notification_session_factory() as session:
        delivered = await process_pending_notifications(
            session,
            worker_id="worker-one",
            sender=sender,
        )

    notification = await _get_notification(
        notification_session_factory,
        notification_id,
    )

    assert delivered == 1
    assert notification.status is NotificationStatus.SENT
    assert notification.sent_at is not None
    assert notification.provider_message_id is not None
    assert len(sender.messages) == 1
