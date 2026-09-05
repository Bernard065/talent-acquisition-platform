"""Version 1 candidate HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.candidates import (
    CandidateCreateRequest,
    CandidateResponse,
)
from app.core.authorization import TenantContext
from app.services.candidates import (
    CreateCandidateCommand,
    create_candidate,
    get_candidate,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

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
