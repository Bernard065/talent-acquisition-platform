"""Tenant-authenticated job-posting management read endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.job_postings import (
    JobPostingListResponse,
    JobPostingResponse,
)
from app.core.authorization import TenantContext
from app.domains.job_postings.enums import EmploymentType, JobPostingStatus
from app.services.job_postings import (
    JobPostingSearchFilters,
    get_job_posting,
    list_job_postings,
)

router = APIRouter(tags=["Job postings"])

_PRIVATE_NO_STORE = "private, no-store"


@router.get(
    "/job-postings",
    response_model=JobPostingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List tenant job postings",
)
async def list_tenant_job_postings(
    response: Response,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    requisition_id: UUID | None = None,
    posting_status: Annotated[
        JobPostingStatus | None,
        Query(alias="status"),
    ] = None,
    employment_type: EmploymentType | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> JobPostingListResponse:
    """Return tenant-scoped job postings using stable cursor pagination."""
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE

    page = await list_job_postings(
        session=session,
        context=tenant_context,
        filters=JobPostingSearchFilters(
            requisition_id=requisition_id,
            status=posting_status,
            employment_type=employment_type,
            published_after=published_after,
            published_before=published_before,
        ),
        cursor=cursor,
        limit=limit,
    )

    return JobPostingListResponse(
        items=[
            JobPostingResponse.model_validate(job_posting)
            for job_posting in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/job-postings/{job_posting_id}",
    response_model=JobPostingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a tenant job posting",
)
async def get_tenant_job_posting(
    job_posting_id: UUID,
    response: Response,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobPostingResponse:
    """Return one job posting only when it belongs to the caller's tenant."""
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE

    job_posting = await get_job_posting(
        session=session,
        context=tenant_context,
        job_posting_id=job_posting_id,
    )
    return JobPostingResponse.model_validate(job_posting)
