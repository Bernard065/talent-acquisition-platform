"""Private HTTP endpoints for candidate retention-review evidence."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.candidate_retention_reviews import (
    CandidateRetentionExecutionRequest,
    CandidateRetentionExecutionResponse,
    CandidateRetentionReviewChecklistResponse,
    CandidateRetentionReviewCreateRequest,
    CandidateRetentionReviewListResponse,
    CandidateRetentionReviewResponse,
)
from app.core.authorization import TenantContext
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.domains.candidates.retention_review import CandidateRetentionReviewChecklist
from app.services.candidate_retention_execution import (
    execute_candidate_retention_recommendation,
)
from app.services.candidate_retention_reviews import (
    RecordCandidateRetentionReviewCommand,
    list_candidate_retention_reviews,
    record_candidate_retention_review,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(
    prefix="/candidates/{candidate_id}/retention-reviews",
    tags=["Candidate retention reviews"],
)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _to_response(
    review: CandidateRetentionReview,
) -> CandidateRetentionReviewResponse:
    """Serialize controlled evidence, never candidate profile details."""
    return CandidateRetentionReviewResponse(
        id=review.id,
        candidate_id=review.candidate_id,
        policy_id=review.policy_id,
        policy_version=review.policy_version,
        unsuccessful_applicant_days=review.unsuccessful_applicant_days,
        withdrawn_applicant_days=review.withdrawn_applicant_days,
        talent_pool_days=review.talent_pool_days,
        hired_recruiting_copy_days=review.hired_recruiting_copy_days,
        review_number=review.review_number,
        purpose=review.purpose,
        disposition=review.disposition,
        reason_code=review.reason_code,
        checklist=CandidateRetentionReviewChecklistResponse(
            active_matters_reviewed=review.active_matters_reviewed,
            legal_holds_reviewed=review.legal_holds_reviewed,
            other_lawful_basis_reviewed=review.other_lawful_basis_reviewed,
            employee_obligations_reviewed=review.employee_obligations_reviewed,
            external_processors_reviewed=review.external_processors_reviewed,
            backup_restore_safeguards_reviewed=(review.backup_restore_safeguards_reviewed),
        ),
        reviewed_by_subject=review.reviewed_by_subject,
        reviewed_at=review.reviewed_at,
        next_review_at=review.next_review_at,
    )


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Disable shared and browser caching for sensitive write responses."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "",
    response_model=CandidateRetentionReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a candidate retention review",
)
async def record_candidate_retention_review_endpoint(
    candidate_id: UUID,
    payload: CandidateRetentionReviewCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Append review evidence; an erasure recommendation never triggers deletion."""

    async def operation() -> tuple[int, dict[str, Any]]:
        review = await record_candidate_retention_review(
            session,
            context=context,
            candidate_id=candidate_id,
            command=RecordCandidateRetentionReviewCommand(
                policy_id=payload.policy_id,
                purpose=payload.purpose,
                disposition=payload.disposition,
                reason_code=payload.reason_code,
                checklist=CandidateRetentionReviewChecklist(**payload.checklist.model_dump()),
                next_review_at=payload.next_review_at,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            _to_response(review).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate.retention_review.create",
        payload={
            "candidate_id": str(candidate_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)


@router.get(
    "",
    response_model=CandidateRetentionReviewListResponse,
    summary="List candidate retention-review history",
)
async def list_candidate_retention_reviews_endpoint(
    candidate_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> CandidateRetentionReviewListResponse:
    """Read authorized review history in stable, bounded cursor pages."""
    page = await list_candidate_retention_reviews(
        session,
        context=context,
        candidate_id=candidate_id,
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return CandidateRetentionReviewListResponse(
        items=[_to_response(review) for review in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/{review_id}/execute",
    response_model=CandidateRetentionExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute an approved manual-erasure recommendation",
)
async def execute_candidate_retention_review_endpoint(
    candidate_id: UUID,
    review_id: UUID,
    payload: CandidateRetentionExecutionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Execute an eligible recommendation and queue private document cleanup."""

    async def operation() -> tuple[int, dict[str, Any]]:
        execution = await execute_candidate_retention_recommendation(
            session,
            context=context,
            candidate_id=candidate_id,
            review_id=review_id,
        )
        response = CandidateRetentionExecutionResponse(
            id=execution.id,
            candidate_id=execution.candidate_id,
            review_id=execution.review_id,
            review_number=execution.review_number,
            policy_version=execution.policy_version,
            executed_by_subject=execution.executed_by_subject,
            executed_at=execution.executed_at,
        )
        return status.HTTP_202_ACCEPTED, response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate.retention_review.execute",
        payload={
            "candidate_id": str(candidate_id),
            "review_id": str(review_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_idempotency_response(result)
