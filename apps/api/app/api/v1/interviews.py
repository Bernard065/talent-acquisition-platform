"""Version 1 interview scheduling HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.interviews import (
    InterviewSessionResponse,
    ScheduleInterviewRequest,
)
from app.core.authorization import TenantContext
from app.domains.interviews.enums import InterviewParticipantRole
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.interview_scheduling import (
    InterviewParticipantCommand,
    ScheduleInterviewCommand,
    schedule_interview,
)

router = APIRouter(
    prefix="/applications",
    tags=["Interviews"],
)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Return private write data without allowing intermediary caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/{application_id}/interviews",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule an interview",
)
async def schedule_interview_endpoint(
    application_id: UUID,
    payload: ScheduleInterviewRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Schedule an interview for an application already in the interview stage."""

    async def operation() -> tuple[int, dict[str, Any]]:
        interview_session = await schedule_interview(
            session,
            context=context,
            application_id=application_id,
            command=ScheduleInterviewCommand(
                scheduled_start_at=payload.scheduled_start_at,
                scheduled_end_at=payload.scheduled_end_at,
                participants=tuple(
                    InterviewParticipantCommand(
                        user_id=participant.user_id,
                        role=InterviewParticipantRole(participant.role),
                    )
                    for participant in payload.participants
                ),
            ),
        )

        return (
            status.HTTP_201_CREATED,
            InterviewSessionResponse.model_validate(interview_session).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="interview.schedule",
        payload={
            "application_id": str(application_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )

    return _private_idempotency_response(result)
