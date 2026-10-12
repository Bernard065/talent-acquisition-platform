"""Tenant-scoped application activity read service."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.identity import User
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)
from app.services.candidate_errors import (
    ApplicationNotFoundError,
    CandidateAccessDeniedError,
)

_APPLICATION_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_PUBLIC_APPLICATION_SUBJECT = "public:job-application"


@dataclass(frozen=True, slots=True)
class ApplicationActivityItem:
    """Safe stage-history fields for rendering an application timeline."""

    id: UUID
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    rejection_reason: ApplicationRejectionReason | None
    actor_display_name: str
    transitioned_at: datetime


def _require_application_read_access(context: TenantContext) -> None:
    if context.roles.isdisjoint(_APPLICATION_READ_ROLES):
        raise CandidateAccessDeniedError(
            "Caller is not permitted to access application activity."
        )


async def list_application_activity(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> list[ApplicationActivityItem]:
    """Return the tenant-owned stage history for one application."""
    _require_application_read_access(context)

    application_exists = await session.scalar(
        select(Application.id).where(
            Application.id == application_id,
            Application.tenant_id == context.tenant_id,
        )
    )
    if application_exists is None:
        raise ApplicationNotFoundError("Application was not found.")

    rows = (
        await session.execute(
            select(ApplicationStageHistory, User.display_name)
            .outerjoin(
                User,
                and_(
                    User.tenant_id == ApplicationStageHistory.tenant_id,
                    User.external_subject
                    == ApplicationStageHistory.transitioned_by_subject,
                ),
            )
            .where(
                ApplicationStageHistory.application_id == application_id,
                ApplicationStageHistory.tenant_id == context.tenant_id,
            )
            .order_by(
                ApplicationStageHistory.transitioned_at.desc(),
                ApplicationStageHistory.id.desc(),
            )
        )
    ).all()

    return [
        ApplicationActivityItem(
            id=history.id,
            from_status=history.from_status,
            to_status=history.to_status,
            rejection_reason=history.rejection_reason,
            actor_display_name=(
                display_name
                or (
                    "Candidate"
                    if history.transitioned_by_subject
                    == _PUBLIC_APPLICATION_SUBJECT
                    else "Former workspace member"
                )
            ),
            transitioned_at=history.transitioned_at,
        )
        for history, display_name in rows
    ]
