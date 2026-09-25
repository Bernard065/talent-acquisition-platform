"""Tenant-scoped retention policy management and non-destructive previews."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.identity import Tenant
from app.db.models.onboarding import OnboardingInstance
from app.db.transactions import transactional
from app.domains.candidates.enums import ApplicationStatus, CandidatePrivacyStatus
from app.domains.candidates.retention import (
    CandidateRetentionIntervals,
    retention_review_after,
)
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus
from app.domains.onboarding.enums import OnboardingInstanceStatus
from app.services.audit import record_audit_event
from app.services.candidate_retention_errors import (
    CandidateRetentionAccessDeniedError,
    CandidateRetentionPolicyNotFoundError,
    CandidateRetentionPolicyStateError,
)

_POLICY_ADMIN_ROLES = frozenset({Role.TENANT_ADMIN})
_PREVIEW_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})
_TERMINAL_APPLICATION_STATUSES = frozenset(
    {
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.HIRED,
    }
)
_CANDIDATE_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class CandidateRetentionPreview:
    """Aggregate dry-run results; deliberately excludes candidate identifiers and PII."""

    policy_id: UUID
    policy_version: int
    evaluated_at: datetime
    candidates_scanned: int
    due_for_review: int
    not_yet_due: int
    excluded_active_application: int
    excluded_incomplete_onboarding: int
    excluded_non_active_privacy_state: int
    not_evaluable: int


@dataclass(frozen=True, slots=True)
class _ApplicationRetentionFact:
    status: ApplicationStatus
    updated_at: datetime
    onboarding_status: OnboardingInstanceStatus | None
    onboarding_completed_at: datetime | None


def _require_role(context: TenantContext, allowed: frozenset[Role]) -> None:
    if not context.roles.intersection(allowed):
        raise CandidateRetentionAccessDeniedError(
            "Insufficient permission to manage candidate retention."
        )


async def create_candidate_retention_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    intervals: CandidateRetentionIntervals | None = None,
) -> CandidateRetentionPolicy:
    """Create a draft policy version using the reviewed proposal as its defaults."""
    _require_role(context, _POLICY_ADMIN_ROLES)
    selected_intervals = intervals or CandidateRetentionIntervals()
    async with transactional(session):
        tenant = await session.scalar(
            select(Tenant).where(Tenant.id == context.tenant_id).with_for_update()
        )
        if tenant is None:
            raise CandidateRetentionPolicyNotFoundError("Tenant was not found.")
        latest_version = await session.scalar(
            select(func.max(CandidateRetentionPolicy.policy_version)).where(
                CandidateRetentionPolicy.tenant_id == context.tenant_id
            )
        )
        policy = CandidateRetentionPolicy(
            tenant_id=context.tenant_id,
            policy_version=(latest_version or 0) + 1,
            status=CandidateRetentionPolicyStatus.DRAFT,
            unsuccessful_applicant_days=selected_intervals.unsuccessful_applicant_days,
            withdrawn_applicant_days=selected_intervals.withdrawn_applicant_days,
            talent_pool_days=selected_intervals.talent_pool_days,
            hired_recruiting_copy_days=selected_intervals.hired_recruiting_copy_days,
            created_by_subject=context.subject,
        )
        session.add(policy)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.retention_policy_drafted",
            entity_type="candidate_retention_policy",
            entity_id=str(policy.id),
            details={"policy_version": policy.policy_version},
        )
    return policy


async def activate_candidate_retention_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    policy_id: UUID,
    now: datetime | None = None,
) -> CandidateRetentionPolicy:
    """Activate one draft version and retire its predecessor atomically."""
    _require_role(context, _POLICY_ADMIN_ROLES)
    activated_at = now or datetime.now(UTC)
    if activated_at.tzinfo is None or activated_at.utcoffset() is None:
        raise ValueError("Policy activation time must be timezone-aware.")

    async with transactional(session):
        tenant = await session.scalar(
            select(Tenant).where(Tenant.id == context.tenant_id).with_for_update()
        )
        if tenant is None:
            raise CandidateRetentionPolicyNotFoundError("Retention policy was not found.")
        policy = await session.scalar(
            select(CandidateRetentionPolicy)
            .where(
                CandidateRetentionPolicy.id == policy_id,
                CandidateRetentionPolicy.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if policy is None:
            raise CandidateRetentionPolicyNotFoundError("Retention policy was not found.")
        if policy.status is not CandidateRetentionPolicyStatus.DRAFT:
            raise CandidateRetentionPolicyStateError(
                "Only a draft retention policy can be activated."
            )

        previous_policies = list(
            await session.scalars(
                select(CandidateRetentionPolicy)
                .where(
                    CandidateRetentionPolicy.tenant_id == context.tenant_id,
                    CandidateRetentionPolicy.status == CandidateRetentionPolicyStatus.ACTIVE,
                )
                .with_for_update()
            )
        )
        for previous in previous_policies:
            previous.status = CandidateRetentionPolicyStatus.RETIRED
        # Flush retirement before activating the replacement to satisfy the
        # per-tenant partial unique index within this transaction.
        await session.flush()

        policy.status = CandidateRetentionPolicyStatus.ACTIVE
        policy.activated_at = activated_at
        policy.activated_by_subject = context.subject
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.retention_policy_activated",
            entity_type="candidate_retention_policy",
            entity_id=str(policy.id),
            details={"policy_version": policy.policy_version},
        )
    return policy


async def preview_candidate_retention(
    session: AsyncSession,
    *,
    context: TenantContext,
    policy_id: UUID,
    as_of: datetime | None = None,
) -> CandidateRetentionPreview:
    """Count records that merit manual review; this function never mutates records."""
    _require_role(context, _PREVIEW_ROLES)
    evaluated_at = as_of or datetime.now(UTC)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("Retention preview time must be timezone-aware.")

    policy = await session.scalar(
        select(CandidateRetentionPolicy).where(
            CandidateRetentionPolicy.id == policy_id,
            CandidateRetentionPolicy.tenant_id == context.tenant_id,
        )
    )
    if policy is None:
        raise CandidateRetentionPolicyNotFoundError("Retention policy was not found.")

    intervals = CandidateRetentionIntervals(
        unsuccessful_applicant_days=policy.unsuccessful_applicant_days,
        withdrawn_applicant_days=policy.withdrawn_applicant_days,
        talent_pool_days=policy.talent_pool_days,
        hired_recruiting_copy_days=policy.hired_recruiting_copy_days,
    )
    counts = {
        "candidates_scanned": 0,
        "due_for_review": 0,
        "not_yet_due": 0,
        "excluded_active_application": 0,
        "excluded_incomplete_onboarding": 0,
        "excluded_non_active_privacy_state": 0,
        "not_evaluable": 0,
    }
    last_candidate_id: UUID | None = None

    while True:
        candidate_query = (
            select(Candidate.id, Candidate.privacy_status)
            .where(Candidate.tenant_id == context.tenant_id)
            .order_by(Candidate.id)
            .limit(_CANDIDATE_BATCH_SIZE)
        )
        if last_candidate_id is not None:
            candidate_query = candidate_query.where(Candidate.id > last_candidate_id)
        candidate_rows = list((await session.execute(candidate_query)).all())
        if not candidate_rows:
            break

        candidate_ids = [row.id for row in candidate_rows]
        last_candidate_id = candidate_ids[-1]
        application_rows = await session.execute(
            select(
                Application.candidate_id,
                Application.status.label("application_status"),
                Application.updated_at.label("application_updated_at"),
                OnboardingInstance.status.label("onboarding_status"),
                OnboardingInstance.completed_at.label("onboarding_completed_at"),
            )
            .outerjoin(
                OnboardingInstance,
                and_(
                    OnboardingInstance.tenant_id == Application.tenant_id,
                    OnboardingInstance.application_id == Application.id,
                ),
            )
            .where(
                Application.tenant_id == context.tenant_id,
                Application.candidate_id.in_(candidate_ids),
            )
        )
        applications_by_candidate: dict[UUID, list[_ApplicationRetentionFact]] = {}
        for row in application_rows:
            applications_by_candidate.setdefault(row.candidate_id, []).append(
                _ApplicationRetentionFact(
                    status=row.application_status,
                    updated_at=row.application_updated_at,
                    onboarding_status=row.onboarding_status,
                    onboarding_completed_at=row.onboarding_completed_at,
                )
            )

        for candidate in candidate_rows:
            counts["candidates_scanned"] += 1
            if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
                counts["excluded_non_active_privacy_state"] += 1
                continue

            applications = applications_by_candidate.get(candidate.id, [])
            if not applications:
                # Consent is not a purpose-specific talent-pool signal.
                counts["not_evaluable"] += 1
                continue

            if any(
                application.status not in _TERMINAL_APPLICATION_STATUSES
                for application in applications
            ):
                counts["excluded_active_application"] += 1
                continue

            deadlines: list[datetime] = []
            incomplete_hired_application = False
            for application in applications:
                if application.status is ApplicationStatus.REJECTED:
                    deadlines.append(
                        retention_review_after(
                            application.updated_at,
                            intervals.unsuccessful_applicant_days,
                        )
                    )
                elif application.status is ApplicationStatus.WITHDRAWN:
                    deadlines.append(
                        retention_review_after(
                            application.updated_at,
                            intervals.withdrawn_applicant_days,
                        )
                    )
                elif application.status is ApplicationStatus.HIRED:
                    if (
                        application.onboarding_status is not OnboardingInstanceStatus.COMPLETED
                        or application.onboarding_completed_at is None
                    ):
                        incomplete_hired_application = True
                    else:
                        deadlines.append(
                            retention_review_after(
                                application.onboarding_completed_at,
                                intervals.hired_recruiting_copy_days,
                            )
                        )

            if incomplete_hired_application:
                counts["excluded_incomplete_onboarding"] += 1
                continue
            if not deadlines:
                counts["not_evaluable"] += 1
                continue

            # Candidate-level data remains while any associated workflow has a
            # later review date; this avoids deleting shared profile data early.
            review_after = max(deadlines)
            if review_after <= evaluated_at:
                counts["due_for_review"] += 1
            else:
                counts["not_yet_due"] += 1

    return CandidateRetentionPreview(
        policy_id=policy.id,
        policy_version=policy.policy_version,
        evaluated_at=evaluated_at.astimezone(UTC),
        **counts,
    )
