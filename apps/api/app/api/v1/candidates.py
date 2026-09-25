"""Version 1 candidate HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.candidate_talent_pool_consent import (
    CandidateTalentPoolConsentGrantRequest,
    CandidateTalentPoolConsentResponse,
    CandidateTalentPoolConsentWithdrawalRequest,
)
from app.api.v1.schemas.candidates import (
    CandidateCreateRequest,
    CandidateListResponse,
    CandidatePrivacyOperationResponse,
    CandidateResponse,
)
from app.core.authorization import TenantContext
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)
from app.services.candidate_privacy import (
    request_candidate_erasure,
    withdraw_candidate_consent,
)
from app.services.candidate_talent_pool_consent import (
    record_candidate_talent_pool_consent,
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


async def _record_talent_pool_consent_endpoint_operation(
    *,
    candidate_id: UUID,
    event_type: CandidateTalentPoolConsentEventType,
    capture_method: CandidateTalentPoolCaptureMethod,
    notice_version: str | None,
    context: TenantContext,
    session: AsyncSession,
    idempotency_key: str,
) -> JSONResponse:
    """Persist and replay one consent event without returning candidate PII."""

    async def operation() -> tuple[int, dict[str, Any]]:
        event = await record_candidate_talent_pool_consent(
            session,
            context=context,
            candidate_id=candidate_id,
            event_type=event_type,
            capture_method=capture_method,
            notice_version=notice_version,
        )
        response = CandidateTalentPoolConsentResponse(
            event_id=event.id,
            candidate_id=event.candidate_id,
            event_version=event.event_version,
            event_type=event.event_type,
            capture_method=event.capture_method,
            notice_version=event.notice_version,
            recorded_at=event.recorded_at,
        )
        response_status = (
            status.HTTP_200_OK
            if event_type is CandidateTalentPoolConsentEventType.WITHDRAWN
            else status.HTTP_201_CREATED
        )
        return response_status, response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"candidate.talent_pool_consent.{event_type.value}",
        payload={
            "candidate_id": str(candidate_id),
            "event_type": event_type.value,
            "capture_method": capture_method.value,
            "notice_version": notice_version,
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


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
    "/{candidate_id}/talent-pool-consent/grant",
    response_model=CandidateTalentPoolConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record explicit talent-pool consent",
)
async def grant_candidate_talent_pool_consent_endpoint(
    candidate_id: UUID,
    payload: CandidateTalentPoolConsentGrantRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record the candidate's distinct consent to future-role consideration."""
    return await _record_talent_pool_consent_endpoint_operation(
        candidate_id=candidate_id,
        event_type=CandidateTalentPoolConsentEventType.GRANTED,
        capture_method=CandidateTalentPoolCaptureMethod(payload.capture_method),
        notice_version=payload.notice_version,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{candidate_id}/talent-pool-consent/renew",
    response_model=CandidateTalentPoolConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Renew explicit talent-pool consent",
)
async def renew_candidate_talent_pool_consent_endpoint(
    candidate_id: UUID,
    payload: CandidateTalentPoolConsentGrantRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Renew an active consent using the currently reviewed notice version."""
    return await _record_talent_pool_consent_endpoint_operation(
        candidate_id=candidate_id,
        event_type=CandidateTalentPoolConsentEventType.RENEWED,
        capture_method=CandidateTalentPoolCaptureMethod(payload.capture_method),
        notice_version=payload.notice_version,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{candidate_id}/talent-pool-consent/withdraw",
    response_model=CandidateTalentPoolConsentResponse,
    status_code=status.HTTP_200_OK,
    summary="Withdraw talent-pool consent",
)
async def withdraw_candidate_talent_pool_consent_endpoint(
    candidate_id: UUID,
    payload: CandidateTalentPoolConsentWithdrawalRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """End future-role consent without changing generic application consent."""
    return await _record_talent_pool_consent_endpoint_operation(
        candidate_id=candidate_id,
        event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
        capture_method=CandidateTalentPoolCaptureMethod(payload.capture_method),
        notice_version=None,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
    )


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
