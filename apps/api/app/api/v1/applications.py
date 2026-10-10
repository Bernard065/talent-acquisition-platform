"""Version 1 job-application HTTP endpoints."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.application_pipeline import (
    ApplicationStageTransitionRequest,
)
from app.api.v1.schemas.applications import (
    ApplicationCreateRequest,
    ApplicationListResponse,
    ApplicationPipelineItemResponse,
    ApplicationPipelineListResponse,
    ApplicationResponse,
)
from app.core.authorization import TenantContext
from app.domains.candidates.enums import ApplicationStatus
from app.services.application_pipeline import (
    TransitionApplicationStageCommand,
    transition_application_stage,
)
from app.services.candidates import (
    CreateApplicationCommand,
    create_application,
    get_application,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.recruiting_search import (
    ApplicationSearchFilters,
    search_application_pipeline,
    search_applications,
)

router = APIRouter(prefix="/applications", tags=["Applications"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(
    result: IdempotencyResult,
) -> JSONResponse:
    """Prevent sensitive write responses from being cached."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an application",
)
async def create_application_endpoint(
    payload: ApplicationCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Connect a candidate to an open tenant requisition."""

    async def operation() -> tuple[int, dict[str, Any]]:
        application = await create_application(
            session,
            context=context,
            command=CreateApplicationCommand(
                candidate_id=payload.candidate_id,
                requisition_id=payload.requisition_id,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            ApplicationResponse.model_validate(application).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="application.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )

    return _private_idempotency_response(result)


@router.post(
    "/{application_id}/stage-transitions",
    response_model=ApplicationResponse,
    summary="Transition an application pipeline stage",
)
async def transition_application_stage_endpoint(
    application_id: UUID,
    payload: ApplicationStageTransitionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Transition one tenant-owned application using optimistic concurrency."""

    async def operation() -> tuple[int, dict[str, Any]]:
        application = await transition_application_stage(
            session,
            context=context,
            application_id=application_id,
            command=TransitionApplicationStageCommand(
                target_status=payload.target_status,
                expected_version=payload.expected_version,
                rejection_reason=payload.rejection_reason,
            ),
        )

        return (
            status.HTTP_200_OK,
            ApplicationResponse.model_validate(application).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="application.transition_stage",
        payload={
            "application_id": str(application_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )

    return _private_idempotency_response(result)


@router.get(
    "/pipeline",
    response_model=ApplicationPipelineListResponse,
    summary="Search application pipeline cards",
)
async def search_application_pipeline_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    requisition_id: UUID | None = None,
    candidate_id: UUID | None = None,
    application_status: Annotated[
        ApplicationStatus | None,
        Query(alias="status"),
    ] = None,
    applied_after: datetime | None = None,
    applied_before: datetime | None = None,
) -> ApplicationPipelineListResponse:
    """Return application cards with tenant-scoped candidate and job labels."""

    page = await search_application_pipeline(
        session,
        context=context,
        filters=ApplicationSearchFilters(
            requisition_id=requisition_id,
            candidate_id=candidate_id,
            query=query,
            status=application_status,
            applied_after=applied_after,
            applied_before=applied_before,
        ),
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return ApplicationPipelineListResponse(
        items=[
            ApplicationPipelineItemResponse(
                id=record.application.id,
                candidate_id=record.application.candidate_id,
                candidate_name=record.candidate_name,
                candidate_email=record.candidate_email,
                requisition_id=record.application.requisition_id,
                requisition_title=record.requisition_title,
                status=record.application.status,
                applied_at=record.application.applied_at,
                version=record.application.version,
            )
            for record in page.items
        ],
        next_cursor=page.next_cursor,
        stage_counts=page.stage_counts,
    )


@router.get(
    "",
    response_model=ApplicationListResponse,
    summary="Search applications",
)
async def search_applications_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    requisition_id: UUID | None = None,
    candidate_id: UUID | None = None,
    application_status: Annotated[
        ApplicationStatus | None,
        Query(alias="status"),
    ] = None,
    applied_after: datetime | None = None,
    applied_before: datetime | None = None,
) -> ApplicationListResponse:
    """Search tenant applications using safe filters and keyset pagination."""
    page = await search_applications(
        session,
        context=context,
        filters=ApplicationSearchFilters(
            requisition_id=requisition_id,
            candidate_id=candidate_id,
            query=query,
            status=application_status,
            applied_after=applied_after,
            applied_before=applied_before,
        ),
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return ApplicationListResponse(
        items=[
            ApplicationResponse.model_validate(application)
            for application in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Get an application",
)
async def get_application_endpoint(
    application_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> ApplicationResponse:
    """Return one tenant-owned candidate application."""
    application = await get_application(
        session,
        context=context,
        application_id=application_id,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return ApplicationResponse.model_validate(application)
