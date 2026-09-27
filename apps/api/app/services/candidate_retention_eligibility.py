"""Shared current-workflow checks for candidate retention decisions."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.onboarding import OnboardingInstance
from app.domains.candidates.enums import ApplicationStatus
from app.domains.onboarding.enums import OnboardingInstanceStatus

_TERMINAL_APPLICATION_STATUSES = frozenset(
    {
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.HIRED,
    }
)


async def candidate_has_active_workflow(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    include_incomplete_hired_onboarding: bool = False,
) -> bool:
    """Check active applications and, when requested, unfinished hired onboarding."""
    active_application = await session.scalar(
        select(Application.id)
        .where(
            Application.tenant_id == tenant_id,
            Application.candidate_id == candidate_id,
            Application.status.not_in(_TERMINAL_APPLICATION_STATUSES),
        )
        .limit(1)
    )
    if active_application is not None:
        return True
    if not include_incomplete_hired_onboarding:
        return False

    incomplete_hired_application = await session.scalar(
        select(Application.id)
        .outerjoin(
            OnboardingInstance,
            and_(
                OnboardingInstance.application_id == Application.id,
                OnboardingInstance.tenant_id == Application.tenant_id,
            ),
        )
        .where(
            Application.tenant_id == tenant_id,
            Application.candidate_id == candidate_id,
            Application.status == ApplicationStatus.HIRED,
            or_(
                OnboardingInstance.id.is_(None),
                OnboardingInstance.status != OnboardingInstanceStatus.COMPLETED,
                OnboardingInstance.completed_at.is_(None),
            ),
        )
        .limit(1)
    )
    return incomplete_hired_application is not None
