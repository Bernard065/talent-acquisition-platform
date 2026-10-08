"""Version 1 private interview calendar search endpoint."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.interviews import (
    InterviewSearchListResponse,
    InterviewSearchResultResponse,
    InterviewSessionResponse,
)
from app.core.authorization import TenantContext
from app.domains.interviews.enums import InterviewSessionStatus
from app.services.interview_search import (
    InterviewSearchFilters,
    get_interview_session,
    search_interviews,
)

router = APIRouter(prefix="/interviews", tags=["Interviews"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/{interview_session_id}",
    response_model=InterviewSessionResponse,
    summary="Get one interview session",
)
async def get_interview_session_endpoint(
    interview_session_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewSessionResponse:
    """Return one interview visible to the caller without feedback content."""
    interview = await get_interview_session(
        session,
        context=context,
        interview_session_id=interview_session_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return InterviewSessionResponse.model_validate(interview)


@router.get(
    "",
    response_model=InterviewSearchListResponse,
    summary="Search interview schedule",
)
async def search_interviews_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    application_id: UUID | None = None,
    participant_user_id: UUID | None = None,
    interview_status: Annotated[
        InterviewSessionStatus | None,
        Query(alias="status"),
    ] = None,
    scheduled_after: datetime | None = None,
    scheduled_before: datetime | None = None,
) -> InterviewSearchListResponse:
    """Return the caller-authorized tenant interview calendar."""
    page = await search_interviews(
        session,
        context=context,
        filters=InterviewSearchFilters(
            application_id=application_id,
            participant_user_id=participant_user_id,
            status=interview_status,
            scheduled_after=scheduled_after,
            scheduled_before=scheduled_before,
        ),
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return InterviewSearchListResponse(
        items=[
            InterviewSearchResultResponse.model_validate(interview)
            for interview in page.items
        ],
        next_cursor=page.next_cursor,
    )
