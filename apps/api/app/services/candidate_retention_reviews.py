"""Transactional, tenant-scoped recording of non-destructive retention reviews."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.models.onboarding import OnboardingInstance
from app.db.transactions import transactional
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus
from app.domains.candidates.retention_review import (
    CandidateRetentionReviewChecklist,
    CandidateRetentionReviewIneligibleError,
    CandidateRetentionReviewInputError,
    validate_candidate_retention_review,
)
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewPurpose,
    CandidateRetentionReviewReason,
)
from app.domains.onboarding.enums import OnboardingInstanceStatus
from app.services.audit import record_audit_event
from app.services.candidate_retention_errors import (
    CandidateRetentionPolicyNotFoundError,
)
from app.services.candidate_retention_review_errors import (
    CandidateRetentionReviewAccessDeniedError,
    CandidateRetentionReviewNotFoundError,
    CandidateRetentionReviewStateError,
    CandidateRetentionReviewValidationError,
)

_REVIEW_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})
_TERMINAL_APPLICATION_STATUSES = frozenset(
    {
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.HIRED,
    }
)


@dataclass(frozen=True, slots=True)
class RecordCandidateRetentionReviewCommand:
    """Controlled review evidence; free-form notes are intentionally unsupported."""

    policy_id: UUID
    purpose: CandidateRetentionReviewPurpose
    disposition: CandidateRetentionReviewDisposition
    reason_code: CandidateRetentionReviewReason
    checklist: CandidateRetentionReviewChecklist
    next_review_at: datetime | None


def _require_review_role(context: TenantContext) -> None:
    if context.roles.isdisjoint(_REVIEW_ROLES):
        raise CandidateRetentionReviewAccessDeniedError(
            "Only tenant administrators and people operations may record retention reviews."
        )


async def record_candidate_retention_review(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    command: RecordCandidateRetentionReviewCommand,
    reviewed_at: datetime | None = None,
) -> CandidateRetentionReview:
    """Append one review snapshot without changing candidate or deletion state.

    The candidate lock serializes review numbering with erasure and legal-hold
    operations. An erasure recommendation is a non-binding record only: this
    service never calls the erasure workflow or creates an outbox event.
    """
    _require_review_role(context)
    review_time = reviewed_at or datetime.now(UTC)

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
            raise CandidateRetentionReviewNotFoundError("Candidate was not found.")
        if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
            raise CandidateRetentionReviewStateError(
                "A retention review can only be recorded for an active candidate."
            )

        policy = await session.scalar(
            select(CandidateRetentionPolicy)
            .where(
                CandidateRetentionPolicy.id == command.policy_id,
                CandidateRetentionPolicy.tenant_id == context.tenant_id,
                CandidateRetentionPolicy.status == CandidateRetentionPolicyStatus.ACTIVE,
            )
            .with_for_update()
        )
        if policy is None:
            raise CandidateRetentionPolicyNotFoundError("Active retention policy was not found.")

        active_hold_id = await session.scalar(
            select(CandidateRetentionHold.id)
            .where(
                CandidateRetentionHold.tenant_id == context.tenant_id,
                CandidateRetentionHold.candidate_id == candidate.id,
                CandidateRetentionHold.released_at.is_(None),
            )
            .limit(1)
        )
        has_active_legal_hold = active_hold_id is not None

        active_application_id = await session.scalar(
            select(Application.id)
            .where(
                Application.tenant_id == context.tenant_id,
                Application.candidate_id == candidate.id,
                Application.status.not_in(_TERMINAL_APPLICATION_STATUSES),
            )
            .limit(1)
        )
        has_active_workflow = active_application_id is not None

        if command.disposition is CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE:
            incomplete_hired_onboarding = await session.scalar(
                select(Application.id)
                .outerjoin(
                    OnboardingInstance,
                    and_(
                        OnboardingInstance.application_id == Application.id,
                        OnboardingInstance.tenant_id == Application.tenant_id,
                    ),
                )
                .where(
                    Application.tenant_id == context.tenant_id,
                    Application.candidate_id == candidate.id,
                    Application.status == ApplicationStatus.HIRED,
                    or_(
                        OnboardingInstance.id.is_(None),
                        OnboardingInstance.status != OnboardingInstanceStatus.COMPLETED,
                        OnboardingInstance.completed_at.is_(None),
                    ),
                )
                .limit(1)
            )
            has_active_workflow = has_active_workflow or incomplete_hired_onboarding is not None

        try:
            normalized_reviewed_at, next_review_at = validate_candidate_retention_review(
                disposition=command.disposition,
                reason_code=command.reason_code,
                checklist=command.checklist,
                reviewed_at=review_time,
                next_review_at=command.next_review_at,
                has_active_workflow=has_active_workflow,
                has_active_legal_hold=has_active_legal_hold,
            )
        except CandidateRetentionReviewInputError as error:
            raise CandidateRetentionReviewValidationError(str(error)) from error
        except CandidateRetentionReviewIneligibleError as error:
            raise CandidateRetentionReviewStateError(str(error)) from error

        latest_review_number = await session.scalar(
            select(func.max(CandidateRetentionReview.review_number)).where(
                CandidateRetentionReview.tenant_id == context.tenant_id,
                CandidateRetentionReview.candidate_id == candidate.id,
            )
        )
        review = CandidateRetentionReview(
            tenant_id=context.tenant_id,
            candidate_id=candidate.id,
            policy_id=policy.id,
            policy_version=policy.policy_version,
            unsuccessful_applicant_days=policy.unsuccessful_applicant_days,
            withdrawn_applicant_days=policy.withdrawn_applicant_days,
            talent_pool_days=policy.talent_pool_days,
            hired_recruiting_copy_days=policy.hired_recruiting_copy_days,
            review_number=(latest_review_number or 0) + 1,
            purpose=command.purpose,
            disposition=command.disposition,
            reason_code=command.reason_code,
            active_matters_reviewed=command.checklist.active_matters_reviewed,
            legal_holds_reviewed=command.checklist.legal_holds_reviewed,
            other_lawful_basis_reviewed=command.checklist.other_lawful_basis_reviewed,
            employee_obligations_reviewed=command.checklist.employee_obligations_reviewed,
            external_processors_reviewed=command.checklist.external_processors_reviewed,
            backup_restore_safeguards_reviewed=(
                command.checklist.backup_restore_safeguards_reviewed
            ),
            reviewed_by_subject=context.subject,
            reviewed_at=normalized_reviewed_at,
            next_review_at=next_review_at,
        )
        session.add(review)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.retention_review_recorded",
            entity_type="candidate_retention_review",
            entity_id=str(review.id),
            details={
                "review_number": review.review_number,
                "policy_version": review.policy_version,
                "purpose": review.purpose.value,
                "disposition": review.disposition.value,
                "reason_code": review.reason_code.value,
            },
        )

    return review
