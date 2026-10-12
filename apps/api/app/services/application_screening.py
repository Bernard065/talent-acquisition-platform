"""Tenant-scoped recruiter screening scorecards."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_screening_assessment import (
    ApplicationScreeningAssessment,
)
from app.db.models.identity import User
from app.db.transactions import transactional
from app.domains.applications.screening import ScreeningRecommendation
from app.domains.candidates.enums import ApplicationStatus
from app.services.application_screening_errors import (
    ApplicationScreeningAccessDeniedError,
    ApplicationScreeningConflictError,
    ApplicationScreeningValidationError,
)
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError

_SCREENING_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)
_MAX_CRITERIA = 10


@dataclass(frozen=True, slots=True)
class ScreeningCriterionCommand:
    """One normalized requirement score submitted by a reviewer."""

    criterion: str
    rating: int
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class CreateApplicationScreeningAssessmentCommand:
    """Complete scorecard content for one reviewer."""

    overall_rating: int
    recommendation: ScreeningRecommendation
    criteria: tuple[ScreeningCriterionCommand, ...]
    summary: str


def _require_screening_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_SCREENING_ROLES):
        raise ApplicationScreeningAccessDeniedError(
            "Caller is not permitted to review applications."
        )


def _normalize_command(
    command: CreateApplicationScreeningAssessmentCommand,
) -> tuple[list[dict[str, object]], str]:
    if not 1 <= command.overall_rating <= 5:
        raise ApplicationScreeningValidationError(
            "Overall rating must be between 1 and 5."
        )
    if not 1 <= len(command.criteria) <= _MAX_CRITERIA:
        raise ApplicationScreeningValidationError(
            "Provide between 1 and 10 job requirement criteria."
        )

    criteria: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for item in command.criteria:
        criterion = item.criterion.strip()
        evidence = item.evidence.strip() if item.evidence else None
        if not criterion:
            raise ApplicationScreeningValidationError(
                "Requirement names must not be blank."
            )
        if len(criterion) > 200:
            raise ApplicationScreeningValidationError(
                "Requirement names must not exceed 200 characters."
            )
        if item.rating < 1 or item.rating > 5:
            raise ApplicationScreeningValidationError(
                "Requirement ratings must be between 1 and 5."
            )
        normalized_name = criterion.casefold()
        if normalized_name in seen_names:
            raise ApplicationScreeningValidationError(
                "Each job requirement must be listed only once."
            )
        seen_names.add(normalized_name)
        criteria.append(
            {
                "criterion": criterion,
                "rating": item.rating,
                "evidence": evidence or None,
            }
        )

    summary = command.summary.strip()
    if not summary:
        raise ApplicationScreeningValidationError(
            "Add a summary before submitting the assessment."
        )
    if len(summary) > 5000:
        raise ApplicationScreeningValidationError(
            "Assessment summary must not exceed 5000 characters."
        )
    return criteria, summary


async def list_application_screening_assessments(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> tuple[list[tuple[ApplicationScreeningAssessment, str]], UUID | None]:
    """List submitted assessments without exposing another reviewer's draft."""
    _require_screening_role(context)
    async with transactional(session):
        application_exists = await session.scalar(
            select(Application.id).where(
                Application.id == application_id,
                Application.tenant_id == context.tenant_id,
            )
        )
        if application_exists is None:
            raise ApplicationNotFoundError("Application was not found.")

        reviewer_user_id = await session.scalar(
            select(User.id).where(
                User.tenant_id == context.tenant_id,
                User.external_subject == context.subject,
            )
        )
        if reviewer_user_id is None:
            raise ApplicationScreeningAccessDeniedError(
                "Caller is not permitted to review applications."
            )

        rows = await session.execute(
            select(ApplicationScreeningAssessment, User.display_name)
            .join(User, User.id == ApplicationScreeningAssessment.reviewer_user_id)
            .where(
                ApplicationScreeningAssessment.tenant_id == context.tenant_id,
                ApplicationScreeningAssessment.application_id == application_id,
                User.tenant_id == context.tenant_id,
            )
            .order_by(
                ApplicationScreeningAssessment.submitted_at.desc(),
                ApplicationScreeningAssessment.id.desc(),
            )
        )
        assessments = [
            (assessment, display_name) for assessment, display_name in rows.all()
        ]
        my_assessment_id = next(
            (
                assessment.id
                for assessment, _display_name in assessments
                if assessment.reviewer_user_id == reviewer_user_id
            ),
            None,
        )
        return assessments, my_assessment_id


async def submit_application_screening_assessment(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: CreateApplicationScreeningAssessmentCommand,
) -> tuple[ApplicationScreeningAssessment, str]:
    """Record one immutable assessment while the application is in screening."""
    _require_screening_role(context)
    criteria, summary = _normalize_command(command)

    try:
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
            if application.status is not ApplicationStatus.SCREENING:
                raise ApplicationScreeningConflictError(
                    "Move the application to Screening before submitting an assessment."
                )

            reviewer = await session.scalar(
                select(User).where(
                    User.tenant_id == context.tenant_id,
                    User.external_subject == context.subject,
                )
            )
            if reviewer is None:
                raise ApplicationScreeningAccessDeniedError(
                    "Caller is not permitted to review applications."
                )

            assessment = ApplicationScreeningAssessment(
                tenant_id=context.tenant_id,
                application_id=application_id,
                reviewer_user_id=reviewer.id,
                overall_rating=command.overall_rating,
                recommendation=command.recommendation,
                criteria=criteria,
                summary=summary,
            )
            session.add(assessment)
            await session.flush()
            record_audit_event(
                session,
                context=context,
                action="application.screening_assessment_submitted",
                entity_type="application_screening_assessment",
                entity_id=str(assessment.id),
                details={
                    "application_id": str(application_id),
                    "overall_rating": assessment.overall_rating,
                    "recommendation": assessment.recommendation.value,
                    "criteria_count": len(criteria),
                },
            )
            await session.flush()
            await session.refresh(assessment)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise ApplicationScreeningConflictError(
                "You have already submitted a screening assessment for this application."
            ) from error
        raise

    return assessment, reviewer.display_name
