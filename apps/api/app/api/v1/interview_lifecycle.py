"""Version 1 interview-session lifecycle HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.interview_lifecycle import (
    CancelInterviewSessionRequest,
    CompleteInterviewSessionRequest,
    RescheduleInterviewSessionRequest,
)
from app.api.v1.schemas.interviews import InterviewSessionResponse
from app.core.authorization import TenantContext
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.interview_lifecycle import (
    CancelInterviewSessionCommand,
    CompleteInterviewSessionCommand,
    RescheduleInterviewSessionCommand,
    cancel_interview_session,
    complete_interview_session,
    reschedule_interview_session,
)

router = APIRouter(
    prefix="/interview-sessions",
    tags=["Interview Lifecycle"],
)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Return lifecycle data without allowing intermediary caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/{interview_session_id}/complete",
    response_model=InterviewSessionResponse,
    summary="Complete an interview session",
)
async def complete_interview_session_endpoint(
    interview_session_id: UUID,
    payload: CompleteInterviewSessionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Mark one scheduled interview session as completed."""

    async def operation() -> tuple[int, dict[str, Any]]:
        interview_session = await complete_interview_session(
            session,
            context=context,
            interview_session_id=interview_session_id,
            command=CompleteInterviewSessionCommand(
                expected_version=payload.expected_version,
            ),
        )
        return (
            status.HTTP_200_OK,
            InterviewSessionResponse.model_validate(interview_session).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_session.complete",
        payload={
            "interview_session_id": str(interview_session_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.post(
    "/{interview_session_id}/cancel",
    response_model=InterviewSessionResponse,
    summary="Cancel an interview session",
)
async def cancel_interview_session_endpoint(
    interview_session_id: UUID,
    payload: CancelInterviewSessionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Cancel one scheduled interview session with a controlled reason."""

    async def operation() -> tuple[int, dict[str, Any]]:
        interview_session = await cancel_interview_session(
            session,
            context=context,
            interview_session_id=interview_session_id,
            command=CancelInterviewSessionCommand(
                expected_version=payload.expected_version,
                cancellation_reason=payload.cancellation_reason,
            ),
        )
        return (
            status.HTTP_200_OK,
            InterviewSessionResponse.model_validate(interview_session).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_session.cancel",
        payload={
            "interview_session_id": str(interview_session_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.put(
    "/{interview_session_id}/schedule",
    response_model=InterviewSessionResponse,
    summary="Reschedule an interview session",
)
async def reschedule_interview_session_endpoint(
    interview_session_id: UUID,
    payload: RescheduleInterviewSessionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Move a scheduled interview and its participant reservations."""

    async def operation() -> tuple[int, dict[str, Any]]:
        interview_session = await reschedule_interview_session(
            session,
            context=context,
            interview_session_id=interview_session_id,
            command=RescheduleInterviewSessionCommand(
                expected_version=payload.expected_version,
                scheduled_start_at=payload.scheduled_start_at,
                scheduled_end_at=payload.scheduled_end_at,
            ),
        )
        return (
            status.HTTP_200_OK,
            InterviewSessionResponse.model_validate(interview_session).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview_session.reschedule",
        payload={
            "interview_session_id": str(interview_session_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)
