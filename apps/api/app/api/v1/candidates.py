"""Version 1 candidate HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.candidates import (
    CandidateCreateRequest,
    CandidateListResponse,
    CandidatePrivacyOperationResponse,
    CandidateResponse,
)
from app.core.authorization import TenantContext
from app.domains.candidates.enums import CandidateConsentStatus
from app.services.candidate_privacy import (
    request_candidate_erasure,
    withdraw_candidate_consent,
)
from app.services.candidates import (
    CreateCandidateCommand,
    create_candidate,
    get_candidate,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.recruiting_search import (
    CandidateSearchFilters,
    search_candidates,
)

router = APIRouter(prefix="/candidates", tags=["Candidates"])

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
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a candidate",
)
async def create_candidate_endpoint(
    payload: CandidateCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one tenant-scoped candidate profile."""

    async def operation() -> tuple[int, dict[str, Any]]:
        candidate = await create_candidate(
            session,
            context=context,
            command=CreateCandidateCommand(
                full_name=payload.full_name,
                email=str(payload.email),
                source=payload.source,
                phone=payload.phone,
                location=payload.location,
                source_metadata=payload.source_metadata,
                consent_status=payload.consent_status,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            CandidateResponse.model_validate(candidate).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )

    return _private_idempotency_response(result)


@router.get(
    "",
    response_model=CandidateListResponse,
    summary="Search candidates",
)
async def search_candidates_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    consent_status: CandidateConsentStatus | None = None,
) -> CandidateListResponse:
    """Search candidate records visible to the authenticated tenant."""
    page = await search_candidates(
        session,
        context=context,
        filters=CandidateSearchFilters(
            query=query,
            source=source,
            location=location,
            consent_status=consent_status,
        ),
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return CandidateListResponse(
        items=[
            CandidateResponse.model_validate(candidate)
            for candidate in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
    summary="Get a candidate",
)
async def get_candidate_endpoint(
    candidate_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> CandidateResponse:
    """Return one tenant-owned candidate without enabling enumeration."""
    candidate = await get_candidate(
        session,
        context=context,
        candidate_id=candidate_id,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/consent/withdraw",
    response_model=CandidatePrivacyOperationResponse,
    summary="Withdraw candidate consent",
)
async def withdraw_candidate_consent_endpoint(
    candidate_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record a tenant-authorized consent withdrawal without returning PII."""

    async def operation() -> tuple[int, dict[str, Any]]:
        candidate = await withdraw_candidate_consent(
            session,
            context=context,
            candidate_id=candidate_id,
        )
        return (
            status.HTTP_200_OK,
            CandidatePrivacyOperationResponse(
                candidate_id=candidate.id,
                consent_status=candidate.consent_status,
                privacy_status=candidate.privacy_status,
                erasure_requested_at=candidate.erasure_requested_at,
                erased_at=candidate.erased_at,
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate.consent.withdraw",
        payload={"candidate_id": str(candidate_id)},
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.post(
    "/{candidate_id}/erasure",
    response_model=CandidatePrivacyOperationResponse,
    summary="Request candidate data erasure",
)
async def request_candidate_erasure_endpoint(
    candidate_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Anonymize candidate data and enqueue asynchronous document cleanup."""

    async def operation() -> tuple[int, dict[str, Any]]:
        candidate = await request_candidate_erasure(
            session,
            context=context,
            candidate_id=candidate_id,
        )
        return (
            status.HTTP_202_ACCEPTED,
            CandidatePrivacyOperationResponse(
                candidate_id=candidate.id,
                consent_status=candidate.consent_status,
                privacy_status=candidate.privacy_status,
                erasure_requested_at=candidate.erasure_requested_at,
                erased_at=candidate.erased_at,
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate.privacy.erase",
        payload={"candidate_id": str(candidate_id)},
        operation=operation,
    )
    return _private_idempotency_response(result)
