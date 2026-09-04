"""Application service for requisition workflow operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.requisitions.transitions import transition_requisition
from app.services.audit import record_audit_event
from app.services.requisition_errors import (
    RequisitionAccessDeniedError,
    RequisitionNotFoundError,
)

_TRANSITION_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
    }
)


class RequisitionTransitionForbiddenError(RequisitionAccessDeniedError):
    """Raised when a caller lacks permission to change requisition status."""


async def transition_requisition_status(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
    target_status: RequisitionStatus,
) -> Requisition:
    """Transition a tenant-owned requisition and record the audit event.

    The row lock, state update, optimistic-version check, and audit insert are
    committed atomically. A requisition from another tenant is indistinguishable
    from a missing requisition to prevent cross-tenant resource discovery.
    """

    if context.roles.isdisjoint(_TRANSITION_ROLES):
        raise RequisitionTransitionForbiddenError(
            "Caller is not permitted to transition requisitions."
        )

    async with transactional(session):
        statement = (
            select(Requisition)
            .where(
                Requisition.id == requisition_id,
                Requisition.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        result = await session.execute(statement)
        requisition = result.scalar_one_or_none()

        if requisition is None:
            raise RequisitionNotFoundError("Requisition was not found.")

        previous_status = requisition.status
        requisition.status = transition_requisition(
            current_status=previous_status,
            target_status=target_status,
        )

        # Execute the update now so the ORM increments and validates `version`
        # before the related audit event is added.
        await session.flush()
        await session.refresh(requisition)

        record_audit_event(
            session,
            context=context,
            action="requisition.status_changed",
            entity_type="requisition",
            entity_id=str(requisition.id),
            details={
                "previous_status": previous_status.value,
                "target_status": target_status.value,
                "version": requisition.version,
            },
        )

    return requisition
