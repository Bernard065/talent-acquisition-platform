"""Version 1 post-interview hiring decision HTTP endpoint."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.hiring_decisions import (
    HiringDecisionResponse,
    RecordHiringDecisionRequest,
)
from app.core.authorization import TenantContext
from app.services.hiring_decisions import (
    RecordHiringDecisionCommand,
    record_hiring_decision,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(
    prefix="/applications",
    tags=["Hiring Decisions"],
)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_idempotency_response(
    result: IdempotencyResult,
) -> JSONResponse:
    """Prevent debrief decisions from being cached by intermediaries."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/{application_id}/debrief-decision",
    response_model=HiringDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a final post-interview hiring decision",
)
async def record_hiring_decision_endpoint(
    application_id: UUID,
    payload: RecordHiringDecisionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record one final decision and transition the application atomically."""

    async def operation() -> tuple[int, dict[str, Any]]:
        debrief = await record_hiring_decision(
            session,
            context=context,
            application_id=application_id,
            command=RecordHiringDecisionCommand(
                decision=payload.decision,
                expected_application_version=payload.expected_application_version,
                rationale=payload.rationale,
                rejection_reason=payload.rejection_reason,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            HiringDecisionResponse.model_validate(debrief).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="application.record_hiring_decision",
        payload={
            "application_id": str(application_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )

    return _private_idempotency_response(result)
