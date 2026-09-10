"""Anonymous, cacheable HTTP endpoints for public job discovery."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.v1.schemas.public_jobs import (
    PublicJobDetailResponse,
    PublicJobListResponse,
    PublicJobSummaryResponse,
)
from app.domains.job_postings.enums import EmploymentType
from app.services.public_jobs import get_public_job, list_public_jobs

router = APIRouter(prefix="/public/jobs", tags=["Public jobs"])

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]

_PUBLIC_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"


@router.get(
    "",
    response_model=PublicJobListResponse,
    summary="Search published jobs",
)
async def list_public_jobs_endpoint(
    response: Response,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    department: Annotated[str | None, Query(max_length=200)] = None,
    employment_type: EmploymentType | None = None,
) -> PublicJobListResponse:
    """Search candidate-visible jobs without requiring authentication."""
    response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL

    page = await list_public_jobs(
        session,
        limit=limit,
        cursor=cursor,
        query=query,
        location=location,
        department=department,
        employment_type=employment_type,
    )

    return PublicJobListResponse(
        items=[
            PublicJobSummaryResponse.model_validate(posting)
            for posting in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{public_id}",
    response_model=PublicJobDetailResponse,
    summary="Get a published job",
)
async def get_public_job_endpoint(
    public_id: UUID,
    response: Response,
    session: DatabaseSession,
) -> PublicJobDetailResponse:
    """Return a job only while it is currently publicly visible."""
    response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL

    posting = await get_public_job(
        session,
        public_id=public_id,
    )
    return PublicJobDetailResponse.model_validate(posting)
