"""Integration tests for requisition workflow transactions."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.requisitions.transitions import InvalidRequisitionTransition
from app.services.requisition_workflow import (
    RequisitionNotFoundError,
    RequisitionTransitionForbiddenError,
    transition_requisition_status,
)


async def _create_requisition(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    status: RequisitionStatus = RequisitionStatus.DRAFT,
) -> UUID:
    """Create a tenant and requisition for one workflow test."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=status,
        created_by_subject="creator-subject",
    )
    session.add(requisition)
    await session.commit()

    return requisition.id


def _context(
    tenant_id: UUID,
    roles: frozenset[Role],
) -> TenantContext:
    """Build a verified-caller equivalent for an application-service test."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="test-request-id",
    )


@pytest.mark.asyncio
async def test_transitions_requisition_and_records_audit_event(
    session: AsyncSession,
) -> None:
    """Transition a requisition and record the corresponding audit event."""
    tenant_id = uuid4()
    requisition_id = await _create_requisition(session, tenant_id=tenant_id)

    requisition = await transition_requisition_status(
        session,
        context=_context(tenant_id, frozenset({Role.RECRUITER})),
        requisition_id=requisition_id,
        target_status=RequisitionStatus.PENDING_APPROVAL,
    )

    assert requisition.status is RequisitionStatus.PENDING_APPROVAL
    assert requisition.version == 2

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == str(requisition_id),
        )
    )

    assert audit_event is not None
    assert audit_event.action == "requisition.status_changed"
    assert audit_event.actor_subject == "recruiter-subject"
    assert audit_event.details == {
        "previous_status": RequisitionStatus.DRAFT.value,
        "target_status": RequisitionStatus.PENDING_APPROVAL.value,
        "version": 2,
    }


@pytest.mark.asyncio
async def test_rejects_transition_for_unauthorized_role(
    session: AsyncSession,
) -> None:
    """Reject a requisition transition when the caller lacks permission."""
    tenant_id = uuid4()
    requisition_id = await _create_requisition(session, tenant_id=tenant_id)

    with pytest.raises(RequisitionTransitionForbiddenError):
        await transition_requisition_status(
            session,
            context=_context(tenant_id, frozenset({Role.INTERVIEWER})),
            requisition_id=requisition_id,
            target_status=RequisitionStatus.PENDING_APPROVAL,
        )

    requisition = await session.get(Requisition, requisition_id)
    assert requisition is not None
    assert requisition.status is RequisitionStatus.DRAFT

    audit_events = await session.scalars(select(AuditEvent))
    assert not list(audit_events)


@pytest.mark.asyncio
async def test_hides_requisition_owned_by_another_tenant(
    session: AsyncSession,
) -> None:
    """Hide a requisition when it belongs to another tenant."""
    owning_tenant_id = uuid4()
    caller_tenant_id = uuid4()
    requisition_id = await _create_requisition(
        session,
        tenant_id=owning_tenant_id,
    )

    with pytest.raises(RequisitionNotFoundError):
        await transition_requisition_status(
            session,
            context=_context(caller_tenant_id, frozenset({Role.RECRUITER})),
            requisition_id=requisition_id,
            target_status=RequisitionStatus.PENDING_APPROVAL,
        )

    requisition = await session.get(Requisition, requisition_id)
    assert requisition is not None
    assert requisition.status is RequisitionStatus.DRAFT


@pytest.mark.asyncio
async def test_invalid_transition_rolls_back_without_audit_event(
    session: AsyncSession,
) -> None:
    """Roll back an invalid transition without creating an audit event."""
    tenant_id = uuid4()
    requisition_id = await _create_requisition(session, tenant_id=tenant_id)

    with pytest.raises(InvalidRequisitionTransition):
        await transition_requisition_status(
            session,
            context=_context(tenant_id, frozenset({Role.RECRUITER})),
            requisition_id=requisition_id,
            target_status=RequisitionStatus.OPEN,
        )

    requisition = await session.get(Requisition, requisition_id)
    assert requisition is not None
    assert requisition.status is RequisitionStatus.DRAFT

    audit_events = await session.scalars(select(AuditEvent))
    assert not list(audit_events)
