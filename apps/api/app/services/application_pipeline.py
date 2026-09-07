"""Tenant-scoped application pipeline transition service."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.transactions import transactional
from app.domains.applications.transitions import (
    validate_application_transition,
)
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)
from app.services.application_pipeline_errors import (
    ApplicationPipelineAccessDeniedError,
    ApplicationRejectionReasonError,
    ApplicationVersionConflictError,
)
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError

_PIPELINE_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)


@dataclass(frozen=True, slots=True)
class TransitionApplicationStageCommand:
    """Validated input for one optimistic-concurrency stage transition."""

    target_status: ApplicationStatus
    expected_version: int
    rejection_reason: ApplicationRejectionReason | None = None

    def __post_init__(self) -> None:
        if self.expected_version < 1:
            raise ValueError("Application expected version must be at least 1.")

        is_rejection = self.target_status is ApplicationStatus.REJECTED

        if is_rejection and self.rejection_reason is None:
            raise ApplicationRejectionReasonError(
                "A rejection reason is required when rejecting an application."
            )

        if not is_rejection and self.rejection_reason is not None:
            raise ApplicationRejectionReasonError(
                "A rejection reason is valid only when rejecting an application."
            )


def _require_pipeline_write_access(context: TenantContext) -> None:
    """Restrict pipeline changes to authorized recruiting operations roles."""
    if context.roles.isdisjoint(_PIPELINE_WRITE_ROLES):
        raise ApplicationPipelineAccessDeniedError(
            "Caller is not permitted to change application stages."
        )


async def transition_application_stage(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: TransitionApplicationStageCommand,
) -> Application:
    """Atomically transition one tenant-owned application and append history."""
    _require_pipeline_write_access(context)

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

        previous_status = application.status
        validate_application_transition(
            previous_status,
            command.target_status,
        )

        application.status = command.target_status

        session.add(
            ApplicationStageHistory(
                tenant_id=context.tenant_id,
                application_id=application.id,
                from_status=previous_status,
                to_status=command.target_status,
                rejection_reason=command.rejection_reason,
                transitioned_by_subject=context.subject,
            )
        )
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="application.stage_changed",
            entity_type="application",
            entity_id=str(application.id),
            details={
                "previous_status": previous_status.value,
                "target_status": command.target_status.value,
                "rejection_reason": (
                    command.rejection_reason.value
                    if command.rejection_reason is not None
                    else None
                ),
                "version": application.version,
            },
        )
        await session.flush()

    return application
