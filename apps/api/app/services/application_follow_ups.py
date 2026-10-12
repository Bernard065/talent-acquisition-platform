"""Tenant-scoped application follow-up actions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_follow_up import ApplicationFollowUp
from app.db.transactions import transactional
from app.services.application_follow_up_errors import (
    ActiveApplicationFollowUpExistsError,
    ApplicationFollowUpAccessDeniedError,
    ApplicationFollowUpNotFoundError,
    ApplicationFollowUpValidationError,
    ApplicationFollowUpVersionConflictError,
)
from app.services.audit import record_audit_event

_FOLLOW_UP_WRITE_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)


@dataclass(frozen=True, slots=True)
class ApplicationFollowUpCommand:
    """Validated user input for creating or updating a follow-up."""

    action: str
    due_at: datetime


async def _get_application_for_follow_up(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    lock: bool = False,
) -> Application:
    statement = select(Application).where(
        Application.id == application_id,
        Application.tenant_id == context.tenant_id,
    )
    if lock:
        statement = statement.with_for_update()
    application = await session.scalar(statement)
    if application is None:
        raise ApplicationFollowUpNotFoundError("Application was not found.")

    if context.roles.isdisjoint(_FOLLOW_UP_WRITE_ROLES):
        raise ApplicationFollowUpAccessDeniedError(
            "Caller is not permitted to manage application follow-ups."
        )
    return application


def _validate_command(command: ApplicationFollowUpCommand) -> tuple[str, datetime]:
    action = command.action.strip()
    if not action:
        raise ApplicationFollowUpValidationError(
            "Follow-up action must not be blank."
        )
    if command.due_at.tzinfo is None or command.due_at.utcoffset() is None:
        raise ApplicationFollowUpValidationError(
            "Follow-up due date must include a timezone offset."
        )
    return action, command.due_at.astimezone(UTC)


async def list_application_follow_ups(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> list[ApplicationFollowUp]:
    """List completed and pending follow-ups for one tenant application."""
    async with transactional(session):
        await _get_application_for_follow_up(
            session,
            context=context,
            application_id=application_id,
        )
        result = await session.scalars(
            select(ApplicationFollowUp)
            .where(
                ApplicationFollowUp.tenant_id == context.tenant_id,
                ApplicationFollowUp.application_id == application_id,
            )
            .order_by(
                ApplicationFollowUp.created_at.desc(),
                ApplicationFollowUp.id.desc(),
            )
        )
        return list(result)


async def create_application_follow_up(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: ApplicationFollowUpCommand,
) -> ApplicationFollowUp:
    """Create one pending follow-up for an application owned by the caller."""
    action, due_at = _validate_command(command)
    async with transactional(session):
        await _get_application_for_follow_up(
            session,
            context=context,
            application_id=application_id,
            lock=True,
        )
        existing = await session.scalar(
            select(ApplicationFollowUp.id).where(
                ApplicationFollowUp.tenant_id == context.tenant_id,
                ApplicationFollowUp.application_id == application_id,
                ApplicationFollowUp.completed_at.is_(None),
            )
        )
        if existing is not None:
            raise ActiveApplicationFollowUpExistsError(
                "Complete or update the current follow-up before adding another."
            )

        follow_up = ApplicationFollowUp(
            tenant_id=context.tenant_id,
            application_id=application_id,
            action=action,
            due_at=due_at,
            created_by_subject=context.subject,
        )
        session.add(follow_up)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="application.follow_up_created",
            entity_type="application_follow_up",
            entity_id=str(follow_up.id),
            details={"application_id": str(application_id), "due_at": due_at.isoformat()},
        )
        await session.flush()
        await session.refresh(follow_up)
    return follow_up


async def update_application_follow_up(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    follow_up_id: UUID,
    command: ApplicationFollowUpCommand,
    expected_version: int,
) -> ApplicationFollowUp:
    """Update an active follow-up with optimistic concurrency control."""
    action, due_at = _validate_command(command)
    async with transactional(session):
        await _get_application_for_follow_up(
            session,
            context=context,
            application_id=application_id,
            lock=True,
        )
        follow_up = await session.scalar(
            select(ApplicationFollowUp)
            .where(
                ApplicationFollowUp.id == follow_up_id,
                ApplicationFollowUp.tenant_id == context.tenant_id,
                ApplicationFollowUp.application_id == application_id,
                ApplicationFollowUp.completed_at.is_(None),
            )
            .with_for_update()
        )
        if follow_up is None:
            raise ApplicationFollowUpNotFoundError("Pending follow-up was not found.")
        if follow_up.version != expected_version:
            raise ApplicationFollowUpVersionConflictError(
                "Follow-up has changed since the supplied version."
            )

        follow_up.action = action
        follow_up.due_at = due_at
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="application.follow_up_updated",
            entity_type="application_follow_up",
            entity_id=str(follow_up.id),
            details={"application_id": str(application_id), "due_at": due_at.isoformat()},
        )
        await session.flush()
        await session.refresh(follow_up)
    return follow_up


async def complete_application_follow_up(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    follow_up_id: UUID,
    expected_version: int,
) -> ApplicationFollowUp:
    """Complete a pending follow-up and retain it in the application history."""
    async with transactional(session):
        await _get_application_for_follow_up(
            session,
            context=context,
            application_id=application_id,
            lock=True,
        )
        follow_up = await session.scalar(
            select(ApplicationFollowUp)
            .where(
                ApplicationFollowUp.id == follow_up_id,
                ApplicationFollowUp.tenant_id == context.tenant_id,
                ApplicationFollowUp.application_id == application_id,
                ApplicationFollowUp.completed_at.is_(None),
            )
            .with_for_update()
        )
        if follow_up is None:
            raise ApplicationFollowUpNotFoundError("Pending follow-up was not found.")
        if follow_up.version != expected_version:
            raise ApplicationFollowUpVersionConflictError(
                "Follow-up has changed since the supplied version."
            )

        follow_up.completed_at = datetime.now(UTC)
        follow_up.completed_by_subject = context.subject
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="application.follow_up_completed",
            entity_type="application_follow_up",
            entity_id=str(follow_up.id),
            details={"application_id": str(application_id)},
        )
        await session.flush()
        await session.refresh(follow_up)
    return follow_up
