"""Transactional service for explicit future-opportunity consent evidence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_talent_pool_consent import CandidateTalentPoolConsentEvent
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
    consent_is_active,
)
from app.services.audit import record_audit_event
from app.services.candidate_talent_pool_consent_errors import (
    CandidateTalentPoolConsentAccessDeniedError,
    CandidateTalentPoolConsentNotFoundError,
    CandidateTalentPoolConsentStateError,
    CandidateTalentPoolConsentValidationError,
)

_CONSENT_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)
_ERASURE_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})


def _require_consent_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_CONSENT_ROLES):
        raise CandidateTalentPoolConsentAccessDeniedError(
            "Insufficient permission to record candidate talent-pool consent."
        )


def _validate_provenance(
    *,
    event_type: CandidateTalentPoolConsentEventType,
    capture_method: CandidateTalentPoolCaptureMethod,
    notice_version: str | None,
) -> str | None:
    if capture_method is CandidateTalentPoolCaptureMethod.ERASURE_REQUEST:
        if event_type is not CandidateTalentPoolConsentEventType.WITHDRAWN:
            raise CandidateTalentPoolConsentValidationError(
                "Erasure can only record consent withdrawal."
            )
        return None
    if event_type is not CandidateTalentPoolConsentEventType.WITHDRAWN:
        if notice_version is None or not notice_version.strip():
            raise CandidateTalentPoolConsentValidationError(
                "A consent notice version is required for grant or renewal."
            )
    if notice_version is None:
        return None
    normalized_version = notice_version.strip()
    if not normalized_version or len(normalized_version) > 100:
        raise CandidateTalentPoolConsentValidationError(
            "Consent notice version must be between 1 and 100 characters."
        )
    return normalized_version


async def record_candidate_talent_pool_consent(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    event_type: CandidateTalentPoolConsentEventType,
    capture_method: CandidateTalentPoolCaptureMethod,
    notice_version: str | None,
    recorded_at: datetime | None = None,
) -> CandidateTalentPoolConsentEvent:
    """Append a consent event after validating current state and provenance.

    The candidate lock serializes consent changes with each other and with
    erasure. Repeating withdrawal after it already occurred returns the prior
    event; it does not create duplicate audit or consent records.
    """
    _require_consent_role(context)
    if (
        capture_method is CandidateTalentPoolCaptureMethod.ERASURE_REQUEST
        and context.roles.isdisjoint(_ERASURE_ROLES)
    ):
        raise CandidateTalentPoolConsentAccessDeniedError(
            "Only authorized privacy operators can record erasure-driven withdrawal."
        )
    version = _validate_provenance(
        event_type=event_type,
        capture_method=capture_method,
        notice_version=notice_version,
    )
    timestamp = recorded_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CandidateTalentPoolConsentValidationError(
            "Consent event time must be timezone-aware."
        )
    timestamp = timestamp.astimezone(UTC)

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
            raise CandidateTalentPoolConsentNotFoundError("Candidate was not found.")
        if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
            raise CandidateTalentPoolConsentStateError(
                "Talent-pool consent cannot change for a non-active candidate."
            )

        latest = await session.scalar(
            select(CandidateTalentPoolConsentEvent)
            .where(
                CandidateTalentPoolConsentEvent.tenant_id == context.tenant_id,
                CandidateTalentPoolConsentEvent.candidate_id == candidate.id,
            )
            .order_by(
                CandidateTalentPoolConsentEvent.event_version.desc(),
            )
            .limit(1)
            .with_for_update()
        )
        active = latest is not None and consent_is_active(latest.event_type)
        if latest is not None and timestamp < latest.recorded_at:
            raise CandidateTalentPoolConsentValidationError(
                "Consent event time cannot be earlier than the previous event."
            )

        if event_type is CandidateTalentPoolConsentEventType.GRANTED and active:
            raise CandidateTalentPoolConsentStateError(
                "Talent-pool consent is already active; use renewal instead."
            )
        if event_type is CandidateTalentPoolConsentEventType.RENEWED and not active:
            raise CandidateTalentPoolConsentStateError(
                "Only active talent-pool consent can be renewed."
            )
        if event_type is CandidateTalentPoolConsentEventType.WITHDRAWN:
            if latest is None:
                raise CandidateTalentPoolConsentStateError(
                    "Talent-pool consent has not been granted."
                )
            if not active:
                if latest.event_type is CandidateTalentPoolConsentEventType.WITHDRAWN:
                    return latest
                raise CandidateTalentPoolConsentStateError(
                    "Talent-pool consent is not active."
                )

        event = CandidateTalentPoolConsentEvent(
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            event_version=1 if latest is None else latest.event_version + 1,
            event_type=event_type,
            capture_method=capture_method,
            notice_version=version,
            recorded_by_subject=context.subject,
            recorded_at=timestamp,
        )
        session.add(event)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action=f"candidate.talent_pool_consent_{event_type.value}",
            entity_type="candidate_talent_pool_consent_event",
            entity_id=str(event.id),
            details={
                "event_type": event_type.value,
                "capture_method": capture_method.value,
                "notice_version": version,
            },
        )
    return event


async def get_candidate_talent_pool_consent_state(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> CandidateTalentPoolConsentEvent | None:
    """Return the latest consent event for an active, tenant-owned candidate."""
    _require_consent_role(context)
    candidate = await session.scalar(
        select(Candidate.id).where(
            Candidate.id == candidate_id,
            Candidate.tenant_id == context.tenant_id,
            Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
        )
    )
    if candidate is None:
        raise CandidateTalentPoolConsentNotFoundError("Candidate was not found.")

    latest: CandidateTalentPoolConsentEvent | None = await session.scalar(
        select(CandidateTalentPoolConsentEvent)
        .where(
            CandidateTalentPoolConsentEvent.tenant_id == context.tenant_id,
            CandidateTalentPoolConsentEvent.candidate_id == candidate_id,
        )
        .order_by(CandidateTalentPoolConsentEvent.event_version.desc())
        .limit(1)
    )
    return latest


async def withdraw_talent_pool_consent_for_erasure(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    recorded_at: datetime,
) -> CandidateTalentPoolConsentEvent | None:
    """End any active purpose consent in the candidate-erasure transaction."""
    latest = await session.scalar(
        select(CandidateTalentPoolConsentEvent)
        .where(
            CandidateTalentPoolConsentEvent.tenant_id == context.tenant_id,
            CandidateTalentPoolConsentEvent.candidate_id == candidate_id,
        )
        .order_by(
            CandidateTalentPoolConsentEvent.event_version.desc(),
        )
        .limit(1)
        .with_for_update()
    )
    if latest is None or not consent_is_active(latest.event_type):
        return None
    return await record_candidate_talent_pool_consent(
        session,
        context=context,
        candidate_id=candidate_id,
        event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
        capture_method=CandidateTalentPoolCaptureMethod.ERASURE_REQUEST,
        notice_version=None,
        recorded_at=recorded_at,
    )
