"""Tenant-scoped candidate consent withdrawal and personal-data erasure."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidateConsentStatus, CandidatePrivacyStatus
from app.domains.documents.enums import CandidateDocumentStatus
from app.services.audit import record_audit_event
from app.services.candidate_privacy_errors import (
    CandidatePrivacyAccessDeniedError,
    CandidatePrivacyNotFoundError,
)
from app.services.candidate_retention_errors import CandidateRetentionHoldActiveError
from app.services.outbox import enqueue_outbox_event

_CONSENT_MANAGEMENT_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)
_ERASURE_MANAGEMENT_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})
# Exceeds the maximum configured object upload and malware-scan operation time.
_SIGNED_UPLOAD_GRACE_PERIOD = timedelta(minutes=10)


def _require_roles(context: TenantContext, allowed_roles: frozenset[Role]) -> None:
    if context.roles.isdisjoint(allowed_roles):
        raise CandidatePrivacyAccessDeniedError(
            "Caller is not permitted to manage candidate privacy data."
        )


async def withdraw_candidate_consent(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> Candidate:
    """Withdraw a candidate's recorded consent without deleting recruiting history."""
    _require_roles(context, _CONSENT_MANAGEMENT_ROLES)
    now = datetime.now(UTC)

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == candidate_id,
                Candidate.tenant_id == context.tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ACTIVE,
            )
            .with_for_update()
        )
        if candidate is None:
            raise CandidatePrivacyNotFoundError("Candidate was not found.")

        if candidate.consent_status is CandidateConsentStatus.WITHDRAWN:
            return candidate

        previous_status = candidate.consent_status
        candidate.consent_status = CandidateConsentStatus.WITHDRAWN
        candidate.consent_updated_at = now
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="candidate.consent_withdrawn",
            entity_type="candidate",
            entity_id=str(candidate.id),
            details={
                "previous_status": previous_status.value,
                "consent_status": CandidateConsentStatus.WITHDRAWN.value,
            },
        )

    return candidate


async def request_candidate_erasure(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> Candidate:
    """Anonymize a candidate and enqueue private resume-object removal work.

    Applications and their workflow/audit history remain linked to the
    anonymized candidate row. Document bytes are removed asynchronously after
    outstanding presigned uploads have expired.
    """
    _require_roles(context, _ERASURE_MANAGEMENT_ROLES)
    now = datetime.now(UTC)

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
            raise CandidatePrivacyNotFoundError("Candidate was not found.")

        if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
            return candidate

        active_hold = await session.scalar(
            select(CandidateRetentionHold.id).where(
                CandidateRetentionHold.tenant_id == context.tenant_id,
                CandidateRetentionHold.candidate_id == candidate.id,
                CandidateRetentionHold.released_at.is_(None),
            ).limit(1)
        )
        if active_hold is not None:
            raise CandidateRetentionHoldActiveError(
                "Candidate erasure is blocked by an active retention hold."
            )

        documents = list(
            await session.scalars(
                select(CandidateDocument)
                .where(
                    CandidateDocument.tenant_id == context.tenant_id,
                    CandidateDocument.candidate_id == candidate.id,
                    CandidateDocument.status != CandidateDocumentStatus.DELETED,
                )
                .order_by(CandidateDocument.id)
                .with_for_update()
            )
        )

        previous_consent = candidate.consent_status
        candidate.consent_status = CandidateConsentStatus.WITHDRAWN
        if previous_consent is not CandidateConsentStatus.WITHDRAWN:
            candidate.consent_updated_at = now

        candidate.privacy_status = (
            CandidatePrivacyStatus.ERASURE_PENDING
            if documents
            else CandidatePrivacyStatus.ERASED
        )
        candidate.erasure_requested_at = now
        candidate.erased_at = None if documents else now

        # Use a non-routable opaque address so tenant-local deduplication still
        # works without retaining the candidate's original email address.
        erased_email = f"erased+{candidate.id.hex}@privacy.invalid"
        candidate.full_name = "Erased candidate"
        candidate.email = erased_email
        candidate.normalized_email = erased_email.casefold()
        candidate.phone = None
        candidate.location = None
        candidate.source = "privacy_erasure"
        candidate.source_metadata = {}

        for document in documents:
            document.status = CandidateDocumentStatus.DELETED
            document.deleted_at = now
            document.original_filename = "erased"
            document.declared_content_type = "application/octet-stream"
            document.expected_byte_size = 0
            document.checksum_sha256 = None

            delete_event = enqueue_outbox_event(
                session,
                context=context,
                event_type="candidate_document.privacy_delete_requested",
                aggregate_type="candidate_document",
                aggregate_id=str(document.id),
                deduplication_key=f"candidate_document.privacy_delete:{document.id}",
                payload={
                    "candidate_id": str(candidate.id),
                    "document_id": str(document.id),
                },
            )
            delete_event.next_attempt_at = max(
                now,
                document.upload_authorization_expires_at or now,
            ) + _SIGNED_UPLOAD_GRACE_PERIOD

        await session.flush()

        if previous_consent is not CandidateConsentStatus.WITHDRAWN:
            record_audit_event(
                session,
                context=context,
                action="candidate.consent_withdrawn",
                entity_type="candidate",
                entity_id=str(candidate.id),
                details={
                    "previous_status": previous_consent.value,
                    "consent_status": CandidateConsentStatus.WITHDRAWN.value,
                    "reason": "erasure_request",
                },
            )

        record_audit_event(
            session,
            context=context,
            action="candidate.erasure_requested",
            entity_type="candidate",
            entity_id=str(candidate.id),
            details={
                "document_count": len(documents),
                "privacy_status": candidate.privacy_status.value,
            },
        )

    return candidate


async def complete_candidate_erasure_if_no_documents_remain(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    context: TenantContext,
) -> Candidate | None:
    """Complete erasure after the final document object and metadata are removed."""
    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == candidate_id,
                Candidate.tenant_id == tenant_id,
                Candidate.privacy_status == CandidatePrivacyStatus.ERASURE_PENDING,
            )
            .with_for_update()
        )
        if candidate is None:
            return None

        remaining_documents = await session.scalar(
            select(count(CandidateDocument.id)).where(
                CandidateDocument.tenant_id == tenant_id,
                CandidateDocument.candidate_id == candidate_id,
            )
        )
        if remaining_documents:
            return candidate

        candidate.privacy_status = CandidatePrivacyStatus.ERASED
        candidate.erased_at = datetime.now(UTC)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="candidate.erasure_completed",
            entity_type="candidate",
            entity_id=str(candidate.id),
            details={"privacy_status": CandidatePrivacyStatus.ERASED.value},
        )
        return candidate
