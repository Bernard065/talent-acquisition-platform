"""Tenant-scoped application ownership mutations."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.identity import User, UserRoleAssignment
from app.db.transactions import transactional
from app.services.application_pipeline_errors import (
    ApplicationAssigneeInvalidError,
    ApplicationVersionConflictError,
)
from app.services.audit import record_audit_event
from app.services.candidate_errors import (
    ApplicationNotFoundError,
    CandidateAccessDeniedError,
)

_ASSIGNMENT_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)


@dataclass(frozen=True, slots=True)
class AssignApplicationCommand:
    """Validated input for assigning or unassigning an application."""

    assigned_to_user_id: UUID | None
    expected_version: int

    def __post_init__(self) -> None:
        if self.expected_version < 1:
            raise ValueError("Application expected version must be at least 1.")


def _require_assignment_access(context: TenantContext) -> None:
    if context.roles.isdisjoint(_ASSIGNMENT_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to assign applications."
        )


async def assign_application(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: AssignApplicationCommand,
) -> Application:
    """Assign an application to an eligible tenant member atomically."""
    _require_assignment_access(context)

    async with transactional(session):
        application = await session.scalar(
            select(Application)
            .where(
                Application.id == application_id,
                Application.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if application is None:
            raise ApplicationNotFoundError("Application was not found.")

        if application.version != command.expected_version:
            raise ApplicationVersionConflictError(
                "Application has changed since the supplied version."
            )

        assignee = None
        if command.assigned_to_user_id is not None:
            assignee = await session.scalar(
                select(User)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .where(
                    User.id == command.assigned_to_user_id,
                    User.tenant_id == context.tenant_id,
                    UserRoleAssignment.role.in_(_ASSIGNMENT_ROLES),
                )
                .limit(1)
            )
            if assignee is None:
                raise ApplicationAssigneeInvalidError(
                    "Assignee must be a recruiting team member in this workspace."
                )

        previous_assignee_id = application.assigned_to_user_id
        if previous_assignee_id == command.assigned_to_user_id:
            return application

        application.assigned_to_user_id = command.assigned_to_user_id
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="application.assigned" if assignee is not None else "application.unassigned",
            entity_type="application",
            entity_id=str(application.id),
            details={
                "previous_assignee_user_id": (
                    str(previous_assignee_id) if previous_assignee_id else None
                ),
                "assignee_user_id": str(assignee.id) if assignee else None,
                "application_version": application.version,
            },
        )
        await session.flush()
        await session.refresh(application)

    return application
