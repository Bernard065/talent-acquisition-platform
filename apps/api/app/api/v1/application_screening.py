"""Recruiter screening assessment endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.application_screening import (
    ApplicationScreeningAssessmentCreateRequest,
    ApplicationScreeningAssessmentListResponse,
    ApplicationScreeningAssessmentResponse,
    ScreeningCriterionResponse,
)
from app.core.authorization import TenantContext
from app.db.models.application_screening_assessment import (
    ApplicationScreeningAssessment,
)
from app.services.application_screening import (
    CreateApplicationScreeningAssessmentCommand,
    ScreeningCriterionCommand,
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
    rows, my_assessment_id = await list_application_screening_assessments(
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
                    criteria=tuple(
                        ScreeningCriterionCommand(
                            criterion=item.criterion,
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
