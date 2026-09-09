"""Version 1 private offer workflow HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.offers import (
    CreateOfferRequest,
    ExpectedOfferVersionRequest,
    OfferApprovalDecisionRequest,
    OfferApprovalResponse,
    OfferResponse,
)
from app.core.authorization import TenantContext
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.offers import (
    CreateOfferCommand,
    accept_offer,
    cancel_offer,
    create_offer,
    decide_offer_approval,
    decline_offer,
    send_offer,
    submit_offer_for_approval,
)

router = APIRouter(tags=["Offers"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return a replay-safe response without permitting compensation caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/applications/{application_id}/offers",
    response_model=OfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft offer",
)
async def create_offer_endpoint(
    application_id: UUID,
    payload: CreateOfferRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one private draft offer for an offer-stage application."""

    async def operation() -> tuple[int, dict[str, Any]]:
        offer = await create_offer(
            session,
            context=context,
            application_id=application_id,
            command=CreateOfferCommand(**payload.model_dump()),
        )
        return (
            status.HTTP_201_CREATED,
            OfferResponse.model_validate(offer).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="offer.create",
        payload={
            "application_id": str(application_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/offers/{offer_id}/approval-submissions",
    response_model=OfferApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a draft offer for approval",
)
async def submit_offer_for_approval_endpoint(
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Snapshot the policy and submit the current draft offer."""

    async def operation() -> tuple[int, dict[str, Any]]:
        approval = await submit_offer_for_approval(
            session,
            context=context,
            offer_id=offer_id,
            expected_offer_version=payload.expected_offer_version,
        )
        return (
            status.HTTP_201_CREATED,
            OfferApprovalResponse.model_validate(approval).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"offer.submit_for_approval:{offer_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/offer-approvals/{approval_id}/decisions",
    response_model=OfferApprovalResponse,
    summary="Record the assigned offer approval decision",
)
async def decide_offer_approval_endpoint(
    approval_id: UUID,
    payload: OfferApprovalDecisionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Approve or reject only the caller's current assigned approval step."""

    async def operation() -> tuple[int, dict[str, Any]]:
        approval = await decide_offer_approval(
            session,
            context=context,
            approval_id=approval_id,
            expected_offer_version=payload.expected_offer_version,
            decision=payload.decision,
            comment=payload.comment,
        )
        return (
            status.HTTP_200_OK,
            OfferApprovalResponse.model_validate(approval).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"offer_approval.decide:{approval_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


async def _transition_offer_endpoint(
    *,
    operation_name: str,
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: TenantContext,
    session: AsyncSession,
    idempotency_key: str,
    transition: Any,
) -> JSONResponse:
    """Execute one private, idempotent offer lifecycle transition."""

    async def operation() -> tuple[int, dict[str, Any]]:
        offer = await transition(
            session,
            context=context,
            offer_id=offer_id,
            expected_offer_version=payload.expected_offer_version,
        )
        return (
            status.HTTP_200_OK,
            OfferResponse.model_validate(offer).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"{operation_name}:{offer_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post("/offers/{offer_id}/send", response_model=OfferResponse)
async def send_offer_endpoint(
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Mark an approved offer as sent."""
    return await _transition_offer_endpoint(
        operation_name="offer.send",
        offer_id=offer_id,
        payload=payload,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
        transition=send_offer,
    )


@router.post("/offers/{offer_id}/accept", response_model=OfferResponse)
async def accept_offer_endpoint(
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record acceptance and atomically hire the application."""
    return await _transition_offer_endpoint(
        operation_name="offer.accept",
        offer_id=offer_id,
        payload=payload,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
        transition=accept_offer,
    )


@router.post("/offers/{offer_id}/decline", response_model=OfferResponse)
async def decline_offer_endpoint(
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record that a sent offer was declined."""
    return await _transition_offer_endpoint(
        operation_name="offer.decline",
        offer_id=offer_id,
        payload=payload,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
        transition=decline_offer,
    )


@router.post("/offers/{offer_id}/cancel", response_model=OfferResponse)
async def cancel_offer_endpoint(
    offer_id: UUID,
    payload: ExpectedOfferVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Cancel a non-terminal offer."""
    return await _transition_offer_endpoint(
        operation_name="offer.cancel",
        offer_id=offer_id,
        payload=payload,
        context=context,
        session=session,
        idempotency_key=idempotency_key,
        transition=cancel_offer,
    )
