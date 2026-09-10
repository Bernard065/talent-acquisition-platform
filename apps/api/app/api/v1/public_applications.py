"""Anonymous public job application HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    enforce_public_application_body_limit,
    get_db_session,
    get_public_application_abuse_guard,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.public_applications import (
    PublicApplicationAcceptedResponse,
    SubmitPublicApplicationRequest,
)
from app.core.authorization import TenantContext
from app.services.abuse_control import (
    PublicApplicationAbuseCheck,
    PublicApplicationAbuseGuard,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.public_applications import (
    SubmitPublicApplicationCommand,
    resolve_public_application_tenant,
    submit_public_application,
)

router = APIRouter(prefix="/public", tags=["Public applications"])

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
AbuseGuard = Annotated[
    PublicApplicationAbuseGuard,
    Depends(get_public_application_abuse_guard),
]


@router.post(
    "/jobs/{public_job_id}/applications",
    response_model=PublicApplicationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_public_application_body_limit)],
    summary="Submit a public job application",
)
async def submit_public_application_endpoint(
    public_job_id: UUID,
    payload: SubmitPublicApplicationRequest,
    request: Request,
    session: DatabaseSession,
    abuse_guard: AbuseGuard,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Accept an application without exposing candidate or job state."""
    tenant_id = await resolve_public_application_tenant(
        session,
        public_job_id=public_job_id,
    )
    context = TenantContext(
        tenant_id=tenant_id,
        subject="public:job-application",
        roles=frozenset(),
        request_id=request.headers.get("X-Request-ID", "unknown"),
    )

    async def operation() -> tuple[int, dict[str, Any]]:
        await abuse_guard.verify(
            PublicApplicationAbuseCheck(
                public_job_id=public_job_id,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
                challenge_token=payload.challenge_token,
            )
        )
        await submit_public_application(
            session,
            context=context,
            public_job_id=public_job_id,
            command=SubmitPublicApplicationCommand(
                full_name=payload.full_name,
                email=payload.email,
                phone=payload.phone,
                location=payload.location,
                source_reference=payload.source_reference,
            ),
        )
        return (
            status.HTTP_202_ACCEPTED,
            PublicApplicationAcceptedResponse().model_dump(mode="json"),
        )

    result: IdempotencyResult = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="public_application.submit",
        payload={
            "public_job_id": str(public_job_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    await session.commit()

    response = idempotency_response(result)
    response.headers["Cache-Control"] = "no-store"
    return response
