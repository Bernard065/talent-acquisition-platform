"""PostgreSQL integration tests for tenant-scoped dead-letter inspection."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.outbox.enums import OutboxEventStatus
from app.services.outbox_inspection import list_dead_letter_events
from app.services.outbox_inspection_errors import (
    InvalidOutboxCursorError,
    OutboxInspectionAccessDeniedError,
)


def _context(
    tenant_id: UUID,
    roles: frozenset[Role],
) -> TenantContext:
    """Build a verified caller context for operational-inspection tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="tenant-admin-subject",
        roles=roles,
        request_id="outbox-inspection-test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Persist a tenant required by outbox event foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"outbox-inspection-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


async def _create_dead_letter_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    position: int,
    dead_lettered_at: datetime,
) -> OutboxEvent:
    """Create a terminal outbox event with only safe inspection metadata."""
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="candidate_document.scan_requested",
        aggregate_type="candidate_document",
        aggregate_id=str(uuid4()),
        deduplication_key=f"dead-letter-{tenant_id}-{position}",
        payload={"document_id": str(uuid4())},
        status=OutboxEventStatus.DEAD_LETTERED,
        attempts=3,
        dead_lettered_at=dead_lettered_at,
        last_error="malware_scanner_unavailable",
    )
    session.add(event)
    await session.commit()

    return event


@pytest.mark.asyncio
async def test_requires_tenant_admin_role(
    session: AsyncSession,
) -> None:
    """Prevent non-administrators from viewing operational failure records."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)

    with pytest.raises(OutboxInspectionAccessDeniedError):
        await list_dead_letter_events(
            session,
            context=_context(
                tenant_id,
                frozenset({Role.RECRUITER}),
            ),
        )


@pytest.mark.asyncio
async def test_returns_only_dead_letters_owned_by_callers_tenant(
    session: AsyncSession,
) -> None:
    """Keep dead-letter event metadata isolated between tenants."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    now = datetime.now(UTC)

    await _create_tenant(session, owner_tenant_id)
    await _create_tenant(session, other_tenant_id)

    owned_event = await _create_dead_letter_event(
        session,
        tenant_id=owner_tenant_id,
        position=1,
        dead_lettered_at=now,
    )
    await _create_dead_letter_event(
        session,
        tenant_id=other_tenant_id,
        position=1,
        dead_lettered_at=now + timedelta(seconds=1),
    )

    page = await list_dead_letter_events(
        session,
        context=_context(
            owner_tenant_id,
            frozenset({Role.TENANT_ADMIN}),
        ),
    )

    assert [event.id for event in page.items] == [owned_event.id]
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_paginates_dead_letters_deterministically_with_keyset_cursor(
    session: AsyncSession,
) -> None:
    """Avoid duplicates and omissions across descending dead-letter pages."""
    tenant_id = uuid4()
    now = datetime.now(UTC)
    await _create_tenant(session, tenant_id)

    created = [
        await _create_dead_letter_event(
            session,
            tenant_id=tenant_id,
            position=position,
            dead_lettered_at=now + timedelta(seconds=position),
        )
        for position in range(3)
    ]

    context = _context(
        tenant_id,
        frozenset({Role.TENANT_ADMIN}),
    )

    first_page = await list_dead_letter_events(
        session,
        context=context,
        limit=2,
    )
    assert first_page.next_cursor is not None

    second_page = await list_dead_letter_events(
        session,
        context=context,
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [event.id for event in first_page.items + second_page.items]

    assert returned_ids == [
        created[2].id,
        created[1].id,
        created[0].id,
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        "e30",  # "{}"
        "eyJldmVudF9pZCI6ICJub3QtYS11dWlkIn0",
    ],
)
async def test_rejects_invalid_cursor(
    session: AsyncSession,
    cursor: str,
) -> None:
    """Reject malformed cursors instead of using partial pagination state."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)

    with pytest.raises(InvalidOutboxCursorError):
        await list_dead_letter_events(
            session,
            context=_context(
                tenant_id,
                frozenset({Role.TENANT_ADMIN}),
            ),
            cursor=cursor,
        )
