"""Integration tests for tenant-scoped requisition CRUD services."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.domains.requisitions.enums import RequisitionStatus
from app.services.requisition_errors import (
    RequisitionAccessDeniedError,
    RequisitionNotEditableError,
    RequisitionNotFoundError,
)
from app.services.requisition_workflow import transition_requisition_status
from app.services.requisitions import (
    CreateRequisitionCommand,
    UpdateRequisitionCommand,
    create_requisition,
    get_requisition,
    list_requisitions,
    update_requisition,
)


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified-caller equivalent for service integration tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="test-request-id",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Persist a tenant required by requisition foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_creates_draft_requisition_and_audit_event(
    session: AsyncSession,
) -> None:
    """Create a draft requisition and record its audit event."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    requisition = await create_requisition(
        session,
        context=context,
        command=CreateRequisitionCommand(
            title="Senior Backend Engineer",
            description="Build reliable recruiting workflows.",
            department="Engineering",
            location="Nairobi",
            headcount=2,
        ),
    )

    assert requisition.tenant_id == tenant_id
    assert requisition.status is RequisitionStatus.DRAFT
    assert requisition.created_by_subject == context.subject
    assert requisition.version == 1

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(requisition.id),
            AuditEvent.action == "requisition.created",
        )
    )

    assert audit_event is not None
    assert audit_event.tenant_id == tenant_id
    assert audit_event.actor_subject == context.subject


@pytest.mark.asyncio
async def test_gets_requisition_only_from_callers_tenant(
    session: AsyncSession,
) -> None:
    """Return a requisition only when it belongs to the caller's tenant."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    created = await create_requisition(
        session,
        context=context,
        command=CreateRequisitionCommand(
            title="Recruiting Operations Lead",
            description=None,
            department="People",
            location=None,
            headcount=1,
        ),
    )

    requisition = await get_requisition(
        session,
        context=context,
        requisition_id=created.id,
    )

    assert requisition.id == created.id
    assert requisition.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_hides_requisition_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Raise not-found when another tenant requests the requisition."""
    owning_tenant_id = uuid4()
    await _create_tenant(session, owning_tenant_id)

    created = await create_requisition(
        session,
        context=_context(owning_tenant_id),
        command=CreateRequisitionCommand(
            title="Data Engineer",
            description=None,
            department="Engineering",
            location=None,
            headcount=1,
        ),
    )

    with pytest.raises(RequisitionNotFoundError):
        await get_requisition(
            session,
            context=_context(uuid4()),
            requisition_id=created.id,
        )


@pytest.mark.asyncio
async def test_lists_requisitions_with_keyset_pagination(
    session: AsyncSession,
) -> None:
    """List requisitions using keyset pagination without duplicates."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    created_ids: set[UUID] = set()

    for title in (
        "Backend Engineer",
        "Frontend Engineer",
        "Product Designer",
    ):
        requisition = await create_requisition(
            session,
            context=context,
            command=CreateRequisitionCommand(
                title=title,
                description=None,
                department="Product",
                location=None,
                headcount=1,
            ),
        )
        created_ids.add(requisition.id)

    first_page = await list_requisitions(
        session,
        context=context,
        limit=2,
    )

    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None

    second_page = await list_requisitions(
        session,
        context=context,
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = {
        item.id for item in first_page.items + second_page.items
    }

    assert returned_ids == created_ids
    assert not {item.id for item in first_page.items}.intersection(
        item.id for item in second_page.items
    )


@pytest.mark.asyncio
async def test_updates_only_draft_requisition_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Update a draft requisition and record the changed fields."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    created = await create_requisition(
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

    updated = await update_requisition(
        session,
        context=context,
        requisition_id=created.id,
        command=UpdateRequisitionCommand(
            changes={
                "location": "Nairobi",
                "headcount": 2,
            }
        ),
    )

    assert updated.location == "Nairobi"
    assert updated.headcount == 2
    assert updated.version == 2

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(created.id),
            AuditEvent.action == "requisition.updated",
        )
    )

    assert audit_event is not None
    assert audit_event.details == {
        "changed_fields": ["headcount", "location"],
        "version": 2,
    }


@pytest.mark.asyncio
async def test_rejects_update_of_non_draft_requisition(
    session: AsyncSession,
) -> None:
    """Reject updates when the requisition is no longer a draft."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    await _create_tenant(session, tenant_id)

    created = await create_requisition(
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

    await transition_requisition_status(
        session,
        context=context,
        requisition_id=created.id,
        target_status=RequisitionStatus.PENDING_APPROVAL,
    )

    with pytest.raises(RequisitionNotEditableError):
        await update_requisition(
            session,
            context=context,
            requisition_id=created.id,
            command=UpdateRequisitionCommand(
                changes={"title": "Principal Backend Engineer"}
            ),
        )


@pytest.mark.asyncio
async def test_rejects_write_for_read_only_role(
    session: AsyncSession,
) -> None:
    """Reject requisition writes from read-only roles."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)

    with pytest.raises(RequisitionAccessDeniedError):
        await create_requisition(
            session,
            context=_context(
                tenant_id,
                frozenset({Role.ANALYST}),
            ),
            command=CreateRequisitionCommand(
                title="Backend Engineer",
                description=None,
                department="Engineering",
                location=None,
                headcount=1,
            ),
        )

    audit_events = list(await session.scalars(select(AuditEvent)))
    assert not audit_events
