"""Version 1 private interviewer feedback HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.interview_feedback import (
    InterviewFeedbackDraftRequest,
    InterviewFeedbackDraftUpdateRequest,
    InterviewFeedbackResponse,
    InterviewFeedbackSubmitRequest,
)
from app.core.authorization import TenantContext
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.interview_feedback import (
    CreateInterviewFeedbackDraftCommand,
    SubmitInterviewFeedbackCommand,
    UpdateInterviewFeedbackDraftCommand,
    create_interview_feedback_draft,
    get_owned_interview_feedback,
    submit_interview_feedback,
    update_interview_feedback_draft,
)

router = APIRouter(tags=["Interview Feedback"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Prevent sensitive feedback responses from being cached."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/interview-sessions/{interview_session_id}/feedback",
    response_model=InterviewFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the caller's interview feedback draft",
)
async def create_feedback_draft_endpoint(
    interview_session_id: UUID,
    payload: InterviewFeedbackDraftRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one private feedback draft for the assigned interviewer."""

    async def operation() -> tuple[int, dict[str, Any]]:
        feedback = await create_interview_feedback_draft(
            session,
            context=context,
            interview_session_id=interview_session_id,
            command=CreateInterviewFeedbackDraftCommand(
                overall_rating=payload.overall_rating,
                recommendation=payload.recommendation,
                strengths=payload.strengths,
                concerns=payload.concerns,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            InterviewFeedbackResponse.model_validate(feedback).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_feedback.create_draft",
        payload={
            "interview_session_id": str(interview_session_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.get(
    "/interview-feedback/{feedback_id}",
    response_model=InterviewFeedbackResponse,
    summary="Get the caller's interview feedback",
)
async def get_feedback_endpoint(
    feedback_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewFeedbackResponse:
    """Return only feedback authored by the verified caller."""
    feedback = await get_owned_interview_feedback(
        session,
        context=context,
        feedback_id=feedback_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return InterviewFeedbackResponse.model_validate(feedback)


@router.put(
    "/interview-feedback/{feedback_id}",
    response_model=InterviewFeedbackResponse,
    summary="Replace the caller's feedback draft",
)
async def update_feedback_draft_endpoint(
    feedback_id: UUID,
    payload: InterviewFeedbackDraftUpdateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Replace a private draft using optimistic concurrency."""

    async def operation() -> tuple[int, dict[str, Any]]:
        feedback = await update_interview_feedback_draft(
            session,
            context=context,
            feedback_id=feedback_id,
            command=UpdateInterviewFeedbackDraftCommand(
                expected_version=payload.expected_version,
                overall_rating=payload.overall_rating,
                recommendation=payload.recommendation,
                strengths=payload.strengths,
                concerns=payload.concerns,
            ),
        )
        return (
            status.HTTP_200_OK,
            InterviewFeedbackResponse.model_validate(feedback).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_feedback.update_draft",
        payload={
            "feedback_id": str(feedback_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.post(
    "/interview-feedback/{feedback_id}/submit",
    response_model=InterviewFeedbackResponse,
    summary="Submit the caller's interview feedback",
)
async def submit_feedback_endpoint(
    feedback_id: UUID,
    payload: InterviewFeedbackSubmitRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Submit a complete feedback draft and make it immutable."""

    async def operation() -> tuple[int, dict[str, Any]]:
        feedback = await submit_interview_feedback(
            session,
            context=context,
            feedback_id=feedback_id,
            command=SubmitInterviewFeedbackCommand(
                expected_version=payload.expected_version,
                overall_rating=payload.overall_rating,
                recommendation=payload.recommendation,
                strengths=payload.strengths,
                concerns=payload.concerns,
            ),
        )
        return (
            status.HTTP_200_OK,
            InterviewFeedbackResponse.model_validate(feedback).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_feedback.submit",
        payload={
            "feedback_id": str(feedback_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)
