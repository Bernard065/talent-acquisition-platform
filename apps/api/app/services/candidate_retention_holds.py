"""Tenant-scoped legal-hold lifecycle for candidate records."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.services.audit import record_audit_event
from app.services.candidate_retention_errors import (
    CandidateRetentionAccessDeniedError,
    CandidateRetentionHoldNotFoundError,
    CandidateRetentionHoldStateError,
)

_HOLD_MANAGEMENT_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})


def _require_hold_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_HOLD_MANAGEMENT_ROLES):
        raise CandidateRetentionAccessDeniedError(
            "Insufficient permission to manage candidate retention holds."
        )


def _aware_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Retention hold timestamps must be timezone-aware.")
    return value.astimezone(UTC)


async def place_candidate_retention_hold(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    reason: CandidateRetentionHoldReason,
    now: datetime | None = None,
) -> CandidateRetentionHold:
    """Place or return an existing active reason-coded hold.

    The candidate row is the serialization point shared with erasure, so an
    erasure and hold placement cannot both pass their respective preconditions.
    The audit entry deliberately excludes case narratives and candidate PII.
    """
    _require_hold_role(context)
    created_at = _aware_now(now)

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
            raise CandidateRetentionHoldNotFoundError("Candidate was not found.")
        if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
            raise CandidateRetentionHoldStateError(
                "A hold can only be placed on an active candidate record."
            )

        existing = await session.scalar(
            select(CandidateRetentionHold)
            .where(
                CandidateRetentionHold.tenant_id == context.tenant_id,
                CandidateRetentionHold.candidate_id == candidate.id,
                CandidateRetentionHold.reason == reason,
                CandidateRetentionHold.released_at.is_(None),
            )
            .with_for_update()
        )
        if existing is not None:
            return existing

        hold = CandidateRetentionHold(
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            reason=reason,
            created_by_subject=context.subject,
            created_at=created_at,
        )
        session.add(hold)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.retention_hold_placed",
            entity_type="candidate_retention_hold",
            entity_id=str(hold.id),
            details={"reason": reason.value},
        )
    return hold


async def release_candidate_retention_hold(
    session: AsyncSession,
    *,
    context: TenantContext,
    hold_id: UUID,
    now: datetime | None = None,
) -> CandidateRetentionHold:
    """Release a hold once; repeated release requests are safe and auditable once."""
    _require_hold_role(context)
    released_at = _aware_now(now)

    async with transactional(session):
        hold = await session.scalar(
            select(CandidateRetentionHold)
            .where(
                CandidateRetentionHold.id == hold_id,
                CandidateRetentionHold.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if hold is None:
            raise CandidateRetentionHoldNotFoundError("Retention hold was not found.")
        if hold.released_at is not None:
            return hold

        hold.released_at = released_at
        hold.released_by_subject = context.subject
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.retention_hold_released",
            entity_type="candidate_retention_hold",
            entity_id=str(hold.id),
            details={"reason": hold.reason.value},
        )
    return hold
