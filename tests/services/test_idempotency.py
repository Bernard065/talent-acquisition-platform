"""PostgreSQL integration tests for durable idempotency."""

import asyncio  # noqa: I001
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.services.idempotency import (
    IdempotencyKeyReuseError,
    execute_idempotently,
)
from app.services.requisitions import (
    CreateRequisitionCommand,
    create_requisition,
)


def _context(tenant_id: UUID) -> TenantContext:
    """Build a recruiter context for the given tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Insert and commit a tenant used by an integration test."""
    session.add(
        Tenant(
            id=tenant_id,
            name="Idempotency Test Tenant",
            slug=f"idempotency-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_replays_persisted_response_without_second_write(
    session: AsyncSession,
) -> None:
    """Verify that a repeated key replays the original response."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    async def operation() -> tuple[int, dict[str, Any]]:
        """Create and serialize a requisition for the idempotent operation."""
        requisition = await create_requisition(
            session,
            context=context,
            command=CreateRequisitionCommand(
                title="Backend Engineer",
                description=None,
                department="Engineering",
                location=None,
                headcount=1,
            ),
        )
        return 201, {"id": str(requisition.id)}

    first = await execute_idempotently(
        session,
        context=context,
        key="create-backend-engineer",
        operation_name="requisition.create",
        payload={"title": "Backend Engineer"},
        operation=operation,
    )
    second = await execute_idempotently(
        session,
        context=context,
        key="create-backend-engineer",
        operation_name="requisition.create",
        payload={"title": "Backend Engineer"},
        operation=operation,
    )

    requisition_count = await session.scalar(
        select(count()).select_from(Requisition)
    )

    assert first.replayed is False
    assert second.replayed is True
    assert first.body == second.body
    assert requisition_count == 1


@pytest.mark.asyncio
async def test_rejects_key_reused_for_different_request(
    session: AsyncSession,
) -> None:
    """Verify that a key cannot be reused with a different payload."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    async def operation() -> tuple[int, dict[str, Any]]:
        """Return a representative successful operation response."""
        return 201, {"created": True}

    await execute_idempotently(
        session,
        context=context,
        key="shared-key",
        operation_name="requisition.create",
        payload={"title": "Backend Engineer"},
        operation=operation,
    )

    with pytest.raises(IdempotencyKeyReuseError):
        await execute_idempotently(
            session,
            context=context,
            key="shared-key",
            operation_name="requisition.create",
            payload={"title": "Frontend Engineer"},
            operation=operation,
        )


@pytest.mark.asyncio
async def test_allows_key_reuse_after_expiry(
    session: AsyncSession,
) -> None:
    """Verify that an expired key permits a new operation."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)
    executions = 0

    async def operation() -> tuple[int, dict[str, Any]]:
        """Count each execution and return its sequence number."""
        nonlocal executions
        executions += 1
        return 201, {"execution": executions}

    first = await execute_idempotently(
        session,
        context=context,
        key="expiring-key",
        operation_name="requisition.create",
        payload={"title": "Backend Engineer"},
        operation=operation,
        ttl=timedelta(seconds=0),
    )
    second = await execute_idempotently(
        session,
        context=context,
        key="expiring-key",
        operation_name="requisition.create",
        payload={"title": "Backend Engineer"},
        operation=operation,
    )

    assert first.replayed is False
    assert second.replayed is False
    assert executions == 2


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_create_one_requisition(
    database_engine: AsyncEngine,
) -> None:
    """Verify that concurrent requests create only one requisition."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as seed_session:
        await _create_tenant(seed_session, tenant_id)

    operation_started = asyncio.Event()
    release_operation = asyncio.Event()

    async def invoke(wait_for_release: bool) -> bool:
        """Run one request, optionally pausing its operation."""
        async with session_factory() as session:

            async def operation() -> tuple[int, dict[str, Any]]:
                """Create a requisition after the optional synchronization point."""
                operation_started.set()

                if wait_for_release:
                    await release_operation.wait()

                requisition = await create_requisition(
                    session,
                    context=context,
                    command=CreateRequisitionCommand(
                        title="Backend Engineer",
                        description=None,
                        department="Engineering",
                        location=None,
                        headcount=1,
                    ),
                )
                return 201, {"id": str(requisition.id)}

            result = await execute_idempotently(
                session,
                context=context,
                key="concurrent-create",
                operation_name="requisition.create",
                payload={"title": "Backend Engineer"},
                operation=operation,
            )
            return result.replayed

    first_request = asyncio.create_task(invoke(wait_for_release=True))
    await operation_started.wait()

    second_request = asyncio.create_task(invoke(wait_for_release=False))
    await asyncio.sleep(0)

    release_operation.set()
    first_replayed, second_replayed = await asyncio.gather(
        first_request,
        second_request,
    )

    async with session_factory() as verification_session:
        requisition_count = await verification_session.scalar(
            select(count()).select_from(Requisition)
        )

    assert first_replayed is False
    assert second_replayed is True
    assert requisition_count == 1
