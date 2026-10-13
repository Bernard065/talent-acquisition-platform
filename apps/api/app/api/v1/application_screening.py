"""Recruiter screening assessment endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.application_screening import (
    ApplicationScreeningAssessmentCreateRequest,
    ApplicationScreeningAssessmentListResponse,
    ApplicationScreeningAssessmentResponse,
    ScreeningCandidateComparison,
    ScreeningComparisonPageResponse,
    ScreeningCriterionComparison,
    ScreeningCriterionResponse,
    ScreeningRubricCriterion,
)
from app.core.authorization import TenantContext
from app.db.models.application_screening_assessment import (
    ApplicationScreeningAssessment,
)
from app.services.application_screening import (
    CreateApplicationScreeningAssessmentCommand,
    ScreeningCriterionCommand,
    get_job_screening_comparison,
    list_application_screening_assessments,
    submit_application_screening_assessment,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(tags=["Application Screening"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _assessment_response(
    assessment: ApplicationScreeningAssessment,
    reviewer_display_name: str,
) -> ApplicationScreeningAssessmentResponse:
    return ApplicationScreeningAssessmentResponse(
        id=assessment.id,
        application_id=assessment.application_id,
        reviewer_display_name=reviewer_display_name,
        overall_rating=assessment.overall_rating,
        recommendation=assessment.recommendation,
        criteria=[
            ScreeningCriterionResponse.model_validate(item)
            for item in assessment.criteria
        ],
        summary=assessment.summary,
        rubric_version=assessment.rubric_version,
        submitted_at=assessment.submitted_at,
    )


@router.get(
    "/applications/{application_id}/screening-assessments",
    response_model=ApplicationScreeningAssessmentListResponse,
    summary="List recruiter screening assessments for an application",
)
async def list_screening_assessments_endpoint(
    application_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> ApplicationScreeningAssessmentListResponse:
    rows, my_assessment_id, rubric, rubric_version = await list_application_screening_assessments(
        session,
        context=context,
        application_id=application_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return ApplicationScreeningAssessmentListResponse(
        items=[
            _assessment_response(assessment, display_name)
            for assessment, display_name in rows
        ],
        my_assessment_id=my_assessment_id,
        rubric=[ScreeningRubricCriterion.model_validate(item) for item in rubric],
        rubric_version=rubric_version,
    )


@router.get(
    "/job-postings/{job_posting_id}/screening-comparison",
    response_model=ScreeningComparisonPageResponse,
    summary="Compare candidates currently in screening for a job",
)
async def screening_comparison_endpoint(
    job_posting_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=2048),
) -> ScreeningComparisonPageResponse:
    page = await get_job_screening_comparison(
        session,
        context=context,
        job_posting_id=job_posting_id,
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return ScreeningComparisonPageResponse(
        rubric_version=page.rubric_version,
        rubric=[ScreeningRubricCriterion.model_validate(item) for item in page.rubric],
        items=[
            ScreeningCandidateComparison(
                application_id=item.application_id,
                candidate_name=item.candidate_name,
                applied_at=item.applied_at,
                current_rubric_review_count=item.current_rubric_review_count,
                previous_rubric_review_count=item.previous_rubric_review_count,
                average_overall_rating=item.average_overall_rating,
                advance_count=item.advance_count,
                hold_count=item.hold_count,
                reject_count=item.reject_count,
                criteria=[
                    ScreeningCriterionComparison(
                        criterion_id=criterion.criterion_id,
                        criterion=criterion.criterion,
                        average_rating=criterion.average_rating,
                        assessment_count=criterion.assessment_count,
                    )
                    for criterion in item.criteria
                ],
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/applications/{application_id}/screening-assessments",
    response_model=ApplicationScreeningAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a recruiter screening assessment",
)
async def submit_screening_assessment_endpoint(
    application_id: UUID,
    payload: ApplicationScreeningAssessmentCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    async def operation() -> tuple[int, dict[str, Any]]:
        assessment, reviewer_display_name = (
            await submit_application_screening_assessment(
                session,
                context=context,
                application_id=application_id,
                command=CreateApplicationScreeningAssessmentCommand(
                    overall_rating=payload.overall_rating,
                    recommendation=payload.recommendation,
                    rubric_version=payload.rubric_version,
                    criteria=tuple(
                        ScreeningCriterionCommand(
                            criterion_id=item.criterion_id,
                            rating=item.rating,
                            evidence=item.evidence,
                        )
                        for item in payload.criteria
                    ),
                    summary=payload.summary,
                ),
            )
        )
        return (
            status.HTTP_201_CREATED,
            _assessment_response(
                assessment,
                reviewer_display_name,
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="application.screening_assessment.submit",
        payload={
            "application_id": str(application_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)
