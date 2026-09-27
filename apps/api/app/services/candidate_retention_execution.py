"""Explicit, audited execution of a human-reviewed candidate erasure recommendation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_execution import CandidateRetentionExecution
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
)
from app.services.audit import record_audit_event
from app.services.candidate_privacy import request_candidate_erasure
from app.services.candidate_retention_eligibility import candidate_has_active_workflow
from app.services.candidate_retention_execution_errors import (
    CandidateRetentionExecutionAccessDeniedError,
    CandidateRetentionExecutionNotFoundError,
    CandidateRetentionExecutionStateError,
)

_EXECUTION_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})


def _require_execution_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_EXECUTION_ROLES):
        raise CandidateRetentionExecutionAccessDeniedError(
            "Insufficient permission to execute a candidate retention recommendation."
        )


async def execute_candidate_retention_recommendation(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    review_id: UUID,
    executed_at: datetime | None = None,
) -> CandidateRetentionExecution:
    """Execute the latest eligible recommendation atomically and idempotently.

    Execution requires a different authorized person from the reviewer. The
    candidate row serializes this operation with application creation, hold
    placement, and direct erasure requests. Existing document objects are
    removed asynchronously by the candidate-privacy outbox worker.
    """
    _require_execution_role(context)
    execution_time = executed_at or datetime.now(UTC)
    if execution_time.tzinfo is None or execution_time.utcoffset() is None:
        raise CandidateRetentionExecutionStateError(
            "Execution timestamp must be timezone-aware."
        )
    execution_time = execution_time.astimezone(UTC)

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == candidate_id,
                Candidate.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if candidate is None:
            raise CandidateRetentionExecutionNotFoundError(
                "Candidate retention review was not found."
            )

        existing_execution = await session.scalar(
            select(CandidateRetentionExecution)
            .where(
                CandidateRetentionExecution.tenant_id == context.tenant_id,
                CandidateRetentionExecution.candidate_id == candidate.id,
            )
            .with_for_update()
        )
        if existing_execution is not None:
            if existing_execution.review_id == review_id:
                return existing_execution
            raise CandidateRetentionExecutionStateError(
                "Candidate retention has already been executed."
            )

        if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
            raise CandidateRetentionExecutionStateError(
                "Candidate is no longer eligible for retention execution."
            )

        review = await session.scalar(
            select(CandidateRetentionReview)
            .where(
                CandidateRetentionReview.id == review_id,
                CandidateRetentionReview.tenant_id == context.tenant_id,
                CandidateRetentionReview.candidate_id == candidate.id,
            )
            .with_for_update()
        )
        if review is None:
            raise CandidateRetentionExecutionNotFoundError(
                "Candidate retention review was not found."
            )
        if review.disposition is not CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE:
            raise CandidateRetentionExecutionStateError(
                "Only a manual-erasure recommendation can be executed."
            )
        if review.reviewed_by_subject == context.subject:
            raise CandidateRetentionExecutionAccessDeniedError(
                "The reviewer cannot execute their own recommendation."
            )

        latest_review_number = await session.scalar(
            select(func.max(CandidateRetentionReview.review_number)).where(
                CandidateRetentionReview.tenant_id == context.tenant_id,
                CandidateRetentionReview.candidate_id == candidate.id,
            )
        )
        if latest_review_number != review.review_number:
            raise CandidateRetentionExecutionStateError(
                "Only the latest candidate retention review can be executed."
            )

        active_hold = await session.scalar(
            select(CandidateRetentionHold.id)
            .where(
                CandidateRetentionHold.tenant_id == context.tenant_id,
                CandidateRetentionHold.candidate_id == candidate.id,
                CandidateRetentionHold.released_at.is_(None),
            )
            .with_for_update()
            .limit(1)
        )
        if active_hold is not None:
            raise CandidateRetentionExecutionStateError(
                "An active legal hold blocks candidate retention execution."
            )

        if await candidate_has_active_workflow(
            session,
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            include_incomplete_hired_onboarding=True,
        ):
            raise CandidateRetentionExecutionStateError(
                "An active recruiting or onboarding workflow blocks execution."
            )

        await request_candidate_erasure(
            session,
            context=context,
            candidate_id=candidate.id,
        )

        execution = CandidateRetentionExecution(
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            review_id=review.id,
            review_number=review.review_number,
            policy_version=review.policy_version,
            executed_by_subject=context.subject,
            executed_at=execution_time,
        )
        session.add(execution)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="candidate.retention_erasure_executed",
            entity_type="candidate_retention_execution",
            entity_id=str(execution.id),
            details={
                "review_id": str(review.id),
                "review_number": review.review_number,
                "policy_version": review.policy_version,
            },
        )

    return execution
