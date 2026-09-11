"""Tenant-authenticated job-posting management read endpoints."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.job_postings import (
    CreateJobPostingRequest,
    ExpectedJobPostingVersionRequest,
    JobPostingListResponse,
    JobPostingResponse,
)
from app.core.authorization import TenantContext
from app.domains.job_postings.enums import EmploymentType, JobPostingStatus
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.job_postings import (
    CreateJobPostingCommand,
    JobPostingSearchFilters,
    create_job_posting,
    get_job_posting,
    list_job_postings,
    publish_job_posting,
    unpublish_job_posting,
)

router = APIRouter(tags=["Job postings"])


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return an idempotent private response that cannot be cached."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


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


@router.post(
    "/requisitions/{requisition_id}/job-postings",
    response_model=JobPostingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft job posting",
)
async def create_job_posting_endpoint(
    requisition_id: UUID,
    payload: CreateJobPostingRequest,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one tenant-scoped draft posting from a requisition snapshot."""

    async def operation() -> tuple[int, dict[str, Any]]:
        job_posting = await create_job_posting(
            session,
            context=tenant_context,
            requisition_id=requisition_id,
            command=CreateJobPostingCommand(
                employment_type=payload.employment_type,
                expires_at=payload.expires_at,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            JobPostingResponse.model_validate(job_posting).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=tenant_context,
        key=idempotency_key,
        operation_name="job_posting.create",
        payload={
            "requisition_id": str(requisition_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/job-postings/{job_posting_id}/publish",
    response_model=JobPostingResponse,
    summary="Publish a job posting",
)
async def publish_job_posting_endpoint(
    job_posting_id: UUID,
    payload: ExpectedJobPostingVersionRequest,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Publish a draft or unpublished posting when its requisition is open."""

    async def operation() -> tuple[int, dict[str, Any]]:
        job_posting = await publish_job_posting(
            session,
            context=tenant_context,
            job_posting_id=job_posting_id,
            expected_version=payload.expected_version,
        )
        return (
            status.HTTP_200_OK,
            JobPostingResponse.model_validate(job_posting).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=tenant_context,
        key=idempotency_key,
        operation_name=f"job_posting.publish:{job_posting_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/job-postings/{job_posting_id}/unpublish",
    response_model=JobPostingResponse,
    summary="Unpublish a job posting",
)
async def unpublish_job_posting_endpoint(
    job_posting_id: UUID,
    payload: ExpectedJobPostingVersionRequest,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Remove a published posting from public candidate visibility."""

    async def operation() -> tuple[int, dict[str, Any]]:
        job_posting = await unpublish_job_posting(
            session,
            context=tenant_context,
            job_posting_id=job_posting_id,
            expected_version=payload.expected_version,
        )
        return (
            status.HTTP_200_OK,
            JobPostingResponse.model_validate(job_posting).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=tenant_context,
        key=idempotency_key,
        operation_name=f"job_posting.unpublish:{job_posting_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
