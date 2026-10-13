"""Tenant-scoped recruiter screening scorecards."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_screening_assessment import (
    ApplicationScreeningAssessment,
)
from app.db.models.candidate import Candidate
from app.db.models.identity import User
from app.db.models.job_posting import JobPosting
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
from app.services.recruiting_search import decode_search_cursor, encode_search_cursor

_SCREENING_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)
_MAX_CRITERIA = 10


@dataclass(frozen=True, slots=True)
class ScreeningCriterionCommand:
    """One configured rubric criterion's score submitted by a reviewer."""

    criterion_id: UUID
    rating: int
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class CreateApplicationScreeningAssessmentCommand:
    """Complete scorecard content for one reviewer."""

    overall_rating: int
    recommendation: ScreeningRecommendation
    rubric_version: int
    criteria: tuple[ScreeningCriterionCommand, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class ScreeningCriterionComparisonRecord:
    criterion_id: UUID
    criterion: str
    average_rating: float | None
    assessment_count: int


@dataclass(frozen=True, slots=True)
class ScreeningCandidateComparisonRecord:
    application_id: UUID
    candidate_name: str
    applied_at: datetime
    current_rubric_review_count: int
    previous_rubric_review_count: int
    average_overall_rating: float | None
    advance_count: int
    hold_count: int
    reject_count: int
    criteria: list[ScreeningCriterionComparisonRecord]


@dataclass(frozen=True, slots=True)
class ScreeningComparisonPage:
    rubric: list[dict[str, object]]
    rubric_version: int
    items: list[ScreeningCandidateComparisonRecord]
    next_cursor: str | None


def _require_screening_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_SCREENING_ROLES):
        raise ApplicationScreeningAccessDeniedError(
            "Caller is not permitted to review applications."
        )


async def get_job_screening_comparison(
    session: AsyncSession,
    *,
    context: TenantContext,
    job_posting_id: UUID,
    limit: int,
    cursor: str | None,
) -> ScreeningComparisonPage:
    """Summarize Screening applications against the posting's active rubric."""
    _require_screening_role(context)
    async with transactional(session):
        posting = await session.scalar(
            select(JobPosting).where(
                JobPosting.id == job_posting_id,
                JobPosting.tenant_id == context.tenant_id,
            )
        )
        if posting is None:
            raise ApplicationNotFoundError("Job posting was not found.")

        applications_statement = (
            select(Application, Candidate.full_name)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .where(
                Application.tenant_id == context.tenant_id,
                Application.requisition_id == posting.requisition_id,
                Application.status == ApplicationStatus.SCREENING,
                Candidate.tenant_id == context.tenant_id,
            )
            .order_by(Application.applied_at.desc(), Application.id.desc())
        )
        if cursor:
            cursor_timestamp, cursor_id = decode_search_cursor(cursor)
            applications_statement = applications_statement.where(
                or_(
                    Application.applied_at < cursor_timestamp,
                    and_(
                        Application.applied_at == cursor_timestamp,
                        Application.id < cursor_id,
                    ),
                )
            )

        page_rows = (
            await session.execute(applications_statement.limit(limit + 1))
        ).all()
        has_more = len(page_rows) > limit
        page_rows = page_rows[:limit]
        application_ids = [application.id for application, _ in page_rows]

        assessment_rows: list[ApplicationScreeningAssessment] = []
        if application_ids:
            assessment_rows = list(
                (
                    await session.scalars(
                        select(ApplicationScreeningAssessment).where(
                            ApplicationScreeningAssessment.tenant_id
                            == context.tenant_id,
                            ApplicationScreeningAssessment.application_id.in_(
                                application_ids
                            ),
                        )
                    )
                ).all()
            )

        current_rubric = posting.screening_rubric
        rubric_by_id: dict[UUID, str] = {}
        for item in current_rubric:
            try:
                criterion_id = UUID(str(item.get("id")))
            except (ValueError, TypeError):
                continue
            criterion = item.get("criterion")
            if isinstance(criterion, str) and criterion.strip():
                rubric_by_id[criterion_id] = criterion

        assessments_by_application: dict[UUID, list[ApplicationScreeningAssessment]] = {}
        for assessment in assessment_rows:
            assessments_by_application.setdefault(assessment.application_id, []).append(
                assessment
            )

        records: list[ScreeningCandidateComparisonRecord] = []
        for application, candidate_name in page_rows:
            assessments = assessments_by_application.get(application.id, [])
            current_assessments = [
                assessment
                for assessment in assessments
                if assessment.rubric_version == posting.screening_rubric_version
            ]
            prior_count = len(assessments) - len(current_assessments)
            overall_ratings = [
                assessment.overall_rating for assessment in current_assessments
            ]
            criterion_ratings: dict[UUID, list[int]] = {
                criterion_id: [] for criterion_id in rubric_by_id
            }
            for assessment in current_assessments:
                for value in assessment.criteria:
                    try:
                        criterion_id = UUID(str(value.get("criterion_id")))
                    except (ValueError, TypeError):
                        continue
                    rating = value.get("rating")
                    if criterion_id in criterion_ratings and isinstance(rating, int):
                        criterion_ratings[criterion_id].append(rating)

            records.append(
                ScreeningCandidateComparisonRecord(
                    application_id=application.id,
                    candidate_name=candidate_name,
                    applied_at=application.applied_at,
                    current_rubric_review_count=len(current_assessments),
                    previous_rubric_review_count=prior_count,
                    average_overall_rating=(
                        sum(overall_ratings) / len(overall_ratings)
                        if overall_ratings
                        else None
                    ),
                    advance_count=sum(
                        assessment.recommendation.value == "advance"
                        for assessment in current_assessments
                    ),
                    hold_count=sum(
                        assessment.recommendation.value == "hold"
                        for assessment in current_assessments
                    ),
                    reject_count=sum(
                        assessment.recommendation.value == "reject"
                        for assessment in current_assessments
                    ),
                    criteria=[
                        ScreeningCriterionComparisonRecord(
                            criterion_id=criterion_id,
                            criterion=criterion,
                            average_rating=(
                                sum(criterion_ratings[criterion_id])
                                / len(criterion_ratings[criterion_id])
                                if criterion_ratings[criterion_id]
                                else None
                            ),
                            assessment_count=len(criterion_ratings[criterion_id]),
                        )
                        for criterion_id, criterion in rubric_by_id.items()
                    ],
                )
            )

        next_cursor = None
        if has_more and page_rows:
            last_application = page_rows[-1][0]
            next_cursor = encode_search_cursor(
                timestamp=last_application.applied_at,
                record_id=last_application.id,
            )

        return ScreeningComparisonPage(
            rubric=current_rubric,
            rubric_version=posting.screening_rubric_version,
            items=records,
            next_cursor=next_cursor,
        )


def _normalize_command(
    command: CreateApplicationScreeningAssessmentCommand,
    *,
    rubric: list[dict[str, object]],
) -> tuple[list[dict[str, object]], str]:
    if not 1 <= command.overall_rating <= 5:
        raise ApplicationScreeningValidationError(
            "Overall rating must be between 1 and 5."
        )
    if not rubric:
        raise ApplicationScreeningConflictError(
            "Ask a workspace admin or recruiter to configure this job's screening rubric first."
        )
    if not 1 <= len(rubric) <= _MAX_CRITERIA:
        raise ApplicationScreeningValidationError("The job screening rubric is invalid.")

    submitted_by_id = {str(item.criterion_id): item for item in command.criteria}
    rubric_by_id = {
        str(item.get("id")): item
        for item in rubric
        if isinstance(item, dict) and item.get("id") is not None
    }
    if (
        len(submitted_by_id) != len(command.criteria)
        or set(submitted_by_id) != set(rubric_by_id)
    ):
        raise ApplicationScreeningValidationError(
            "Submit a rating for each current job rubric criterion."
        )

    criteria: list[dict[str, object]] = []
    for criterion_id, rubric_item in rubric_by_id.items():
        item = submitted_by_id[criterion_id]
        criterion_value = rubric_item.get("criterion")
        guidance_value = rubric_item.get("guidance")
        criterion = criterion_value.strip() if isinstance(criterion_value, str) else ""
        guidance = guidance_value.strip() if isinstance(guidance_value, str) else None
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
        criteria.append(
            {
                "criterion_id": criterion_id,
                "criterion": criterion,
                "guidance": guidance or None,
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
) -> tuple[
    list[tuple[ApplicationScreeningAssessment, str]],
    UUID | None,
    list[dict[str, object]],
    int | None,
]:
    """List submitted assessments without exposing another reviewer's draft."""
    _require_screening_role(context)
    async with transactional(session):
        application = await session.scalar(
            select(Application).where(
                Application.id == application_id,
                Application.tenant_id == context.tenant_id,
            )
        )
        if application is None:
            raise ApplicationNotFoundError("Application was not found.")

        posting = await session.scalar(
            select(JobPosting)
            .where(
                JobPosting.tenant_id == context.tenant_id,
                JobPosting.requisition_id == application.requisition_id,
            )
            .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
        )

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
        return (
            assessments,
            my_assessment_id,
            posting.screening_rubric if posting is not None else [],
            posting.screening_rubric_version if posting is not None else None,
        )


async def submit_application_screening_assessment(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: CreateApplicationScreeningAssessmentCommand,
) -> tuple[ApplicationScreeningAssessment, str]:
    """Record one immutable assessment while the application is in screening."""
    _require_screening_role(context)
    summary = command.summary.strip()

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

            posting = await session.scalar(
                select(JobPosting)
                .where(
                    JobPosting.tenant_id == context.tenant_id,
                    JobPosting.requisition_id == application.requisition_id,
                )
                .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
                .limit(1)
                .with_for_update()
            )
            if posting is None:
                raise ApplicationScreeningConflictError(
                    "A job posting is required before this application can be screened."
                )
            if posting.screening_rubric_version != command.rubric_version:
                raise ApplicationScreeningConflictError(
                    "The job screening rubric changed. Reload it before submitting your assessment."
                )
            criteria, summary = _normalize_command(
                command,
                rubric=posting.screening_rubric,
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
                rubric_version=posting.screening_rubric_version,
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
