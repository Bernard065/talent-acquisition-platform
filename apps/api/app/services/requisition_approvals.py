"""Transactional policy administration and requisition approval services."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import Role, TenantContext
from app.db.models.approval import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    RequisitionApproval,
    RequisitionApprovalDecision,
)
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.approvals.enums import ApprovalStatus, RequisitionDecisionStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.requisitions.transitions import transition_requisition
from app.services.approval_errors import (
    ApprovalDecisionAlreadyMadeError,
    ApprovalDecisionForbiddenError,
    ApprovalPolicyAccessDeniedError,
    ApprovalPolicyInvalidError,
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
)
from app.services.audit import record_audit_event
from app.services.requisition_errors import (
    RequisitionAccessDeniedError,
    RequisitionNotFoundError,
)

_POLICY_ADMIN_ROLES = frozenset({Role.TENANT_ADMIN})
_POLICY_SETUP_ROLES = frozenset({Role.TENANT_ADMIN, Role.RECRUITER})
_SUBMITTER_ROLES = frozenset({Role.TENANT_ADMIN, Role.RECRUITER})


async def get_latest_requisition_rejection_feedback(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_ids: list[UUID],
) -> dict[UUID, tuple[str | None, datetime]]:
    """Return the latest rejection feedback only to each requisition's requester."""
    if not requisition_ids:
        return {}

    rows = await session.execute(
        select(
            RequisitionApproval.requisition_id,
            RequisitionApproval.submitted_at,
            RequisitionApprovalDecision.comment,
            RequisitionApprovalDecision.decided_at,
        )
        .join(
            Requisition,
            Requisition.id == RequisitionApproval.requisition_id,
        )
        .join(
            RequisitionApprovalDecision,
            RequisitionApprovalDecision.requisition_approval_id
            == RequisitionApproval.id,
        )
        .where(
            Requisition.id.in_(requisition_ids),
            Requisition.tenant_id == context.tenant_id,
            RequisitionApproval.tenant_id == context.tenant_id,
            RequisitionApproval.status == ApprovalStatus.REJECTED,
            RequisitionApprovalDecision.status == RequisitionDecisionStatus.REJECTED,
            or_(
                Requisition.created_by_subject == context.subject,
                RequisitionApproval.submitted_by_subject == context.subject,
            ),
        )
        .order_by(
            RequisitionApproval.requisition_id,
            RequisitionApproval.submitted_at.desc(),
            RequisitionApproval.id.desc(),
        )
    )

    feedback: dict[UUID, tuple[str | None, datetime]] = {}
    for requisition_id, _submitted_at, comment, decided_at in rows:
        if requisition_id in feedback or decided_at is None:
            continue
        feedback[requisition_id] = (comment, decided_at)

    return feedback


@dataclass(frozen=True, slots=True)
class CreateApprovalPolicyCommand:
    """Input for a named pool of alternative requisition reviewers."""

    name: str
    approver_user_ids: tuple[UUID, ...]
    is_default: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ApprovalPolicyInvalidError("Approval policy name is required.")

        if len(self.name) > 200:
            raise ApprovalPolicyInvalidError(
                "Approval policy name must not exceed 200 characters."
            )

        if len(set(self.approver_user_ids)) != len(self.approver_user_ids):
            raise ApprovalPolicyInvalidError(
                "An approver may appear only once in a policy."
            )


async def get_approval_policy_configuration(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> tuple[ApprovalPolicy | None, list[User], list[UUID]]:
    """Return the tenant's default policy and members available to assign."""
    _require_policy_role(context, _POLICY_SETUP_ROLES)

    policy = await session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.tenant_id == context.tenant_id,
            ApprovalPolicy.is_default.is_(True),
        )
    )
    if Role.TENANT_ADMIN not in context.roles and policy is not None:
        raise ApprovalPolicyAccessDeniedError(
            "This workspace already has a default approval policy. Contact your "
            "workspace admin to change the policy or its approvers. You can still "
            "submit requisitions using the current policy."
        )

    members = list(
        await session.scalars(
            select(User)
            .options(selectinload(User.role_assignments))
            .where(User.tenant_id == context.tenant_id)
            .order_by(User.display_name, User.email)
        )
    )
    approver_user_ids: list[UUID] = []
    if policy is not None:
        approver_user_ids = list(
            await session.scalars(
                select(ApprovalPolicyStep.approver_user_id)
                .where(ApprovalPolicyStep.approval_policy_id == policy.id)
                .order_by(ApprovalPolicyStep.position)
            )
        )

    return policy, members, approver_user_ids


def _require_role(context: TenantContext, allowed_roles: frozenset[Role]) -> None:
    """Enforce service-level authorization without depending on HTTP."""
    if context.roles.isdisjoint(allowed_roles):
        raise RequisitionAccessDeniedError(
            "Caller is not permitted to perform this approval operation."
        )


def _require_policy_role(
    context: TenantContext,
    allowed_roles: frozenset[Role],
) -> None:
    """Give policy-management callers guidance when they lack access."""
    if context.roles.isdisjoint(allowed_roles):
        raise ApprovalPolicyAccessDeniedError(
            "Only workspace admins can manage approval settings. Contact your "
            "workspace admin to create or update the shared approval policy."
        )


async def _tenant_users_by_id(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: tuple[UUID, ...],
) -> dict[UUID, User]:
    """Load users only when they belong to the requested tenant."""
    users = list(
        await session.scalars(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id.in_(user_ids),
            )
        )
    )
    users_by_id = {user.id: user for user in users}

    if len(users_by_id) != len(user_ids):
        raise ApprovalPolicyInvalidError(
            "Every configured approver must belong to the tenant."
        )

    return users_by_id


async def _workspace_admin_user_ids(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[UUID, ...]:
    """Return persisted workspace-admin identities for automatic approval."""
    return tuple(
        await session.scalars(
            select(User.id)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                UserRoleAssignment.role == Role.TENANT_ADMIN,
            )
            .order_by(User.display_name, User.email)
        )
    )


async def create_approval_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateApprovalPolicyCommand,
) -> ApprovalPolicy:
    """Create a policy; recruiters may create only the initial default policy."""
    _require_policy_role(context, _POLICY_SETUP_ROLES)

    async with transactional(session):
        # Serialize policy setup per tenant so concurrent first-time requests
        # cannot race past the default-policy check.
        await session.scalar(
            select(Tenant.id)
            .where(Tenant.id == context.tenant_id)
            .with_for_update()
        )
        current_default = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.tenant_id == context.tenant_id,
                ApprovalPolicy.is_default.is_(True),
            )
            .with_for_update()
        )
        is_admin = Role.TENANT_ADMIN in context.roles
        if not is_admin and (
            Role.RECRUITER not in context.roles
            or not command.is_default
            or current_default is not None
        ):
            raise ApprovalPolicyAccessDeniedError(
                "Recruiters can create the first default approval policy only. "
                "Contact your workspace admin to change the shared approval "
                "policy after setup."
            )

        normalized_name = command.name.strip()
        existing_policy = await session.scalar(
            select(ApprovalPolicy.id).where(
                ApprovalPolicy.tenant_id == context.tenant_id,
                func.lower(ApprovalPolicy.name) == normalized_name.lower(),
            )
        )
        if existing_policy is not None:
            raise ApprovalPolicyInvalidError(
                "An approval policy with that name already exists. "
                "Update the existing policy or choose a different name."
            )

        await _tenant_users_by_id(
            session,
            tenant_id=context.tenant_id,
            user_ids=command.approver_user_ids,
        )
        if command.is_default:
            if current_default is not None:
                current_default.is_default = False
                await session.flush()

        policy = ApprovalPolicy(
            tenant_id=context.tenant_id,
            name=normalized_name,
            is_default=command.is_default,
            is_active=True,
        )
        session.add(policy)
        await session.flush()

        session.add_all(
            [
                ApprovalPolicyStep(
                    approval_policy_id=policy.id,
                    position=position,
                    approver_user_id=user_id,
                )
                for position, user_id in enumerate(command.approver_user_ids, start=1)
            ]
        )
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="approval_policy.created",
            entity_type="approval_policy",
            entity_id=str(policy.id),
            details={
                "is_default": policy.is_default,
                "step_count": len(command.approver_user_ids),
            },
        )

    return policy


async def update_approval_policy_approvers(
    session: AsyncSession,
    *,
    context: TenantContext,
    policy_id: UUID,
    approver_user_ids: tuple[UUID, ...],
) -> ApprovalPolicy:
    """Update alternative reviewers on the current default policy.

    Submitted approvals retain their immutable reviewer snapshots.
    """
    _require_policy_role(context, _POLICY_ADMIN_ROLES)
    if len(approver_user_ids) > 20:
        raise ApprovalPolicyInvalidError("A policy may have at most 20 approvers.")
    if len(set(approver_user_ids)) != len(approver_user_ids):
        raise ApprovalPolicyInvalidError(
            "An approver may appear only once in a policy."
        )

    async with transactional(session):
        policy = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.id == policy_id,
                ApprovalPolicy.tenant_id == context.tenant_id,
                ApprovalPolicy.is_default.is_(True),
                ApprovalPolicy.is_active.is_(True),
            )
            .with_for_update()
        )
        if policy is None:
            raise ApprovalPolicyNotFoundError(
                "The active default approval policy was not found."
            )

        await _tenant_users_by_id(
            session,
            tenant_id=context.tenant_id,
            user_ids=approver_user_ids,
        )
        old_steps = list(
            await session.scalars(
                select(ApprovalPolicyStep)
                .where(ApprovalPolicyStep.approval_policy_id == policy.id)
                .with_for_update()
            )
        )
        for step in old_steps:
            await session.delete(step)
        await session.flush()
        session.add_all(
            [
                ApprovalPolicyStep(
                    approval_policy_id=policy.id,
                    position=position,
                    approver_user_id=user_id,
                )
                for position, user_id in enumerate(approver_user_ids, start=1)
            ]
        )
        policy.version += 1
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="approval_policy.approvers_updated",
            entity_type="approval_policy",
            entity_id=str(policy.id),
            details={"version": policy.version, "step_count": len(approver_user_ids)},
        )

    return policy


async def set_default_approval_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    policy_id: UUID,
) -> ApprovalPolicy:
    """Set one active tenant policy as the default for future submissions."""
    _require_policy_role(context, _POLICY_ADMIN_ROLES)

    async with transactional(session):
        await session.scalar(
            select(Tenant.id)
            .where(Tenant.id == context.tenant_id)
            .with_for_update()
        )
        policy = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.id == policy_id,
                ApprovalPolicy.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if policy is None:
            raise ApprovalPolicyNotFoundError("Approval policy was not found.")

        if not policy.is_active:
            raise ApprovalPolicyInvalidError(
                "An inactive approval policy cannot be the default."
            )

        current_default = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.tenant_id == context.tenant_id,
                ApprovalPolicy.is_default.is_(True),
                ApprovalPolicy.id != policy.id,
            )
            .with_for_update()
        )
        if current_default is not None:
            current_default.is_default = False
            await session.flush()

        policy.is_default = True

        record_audit_event(
            session,
            context=context,
            action="approval_policy.set_default",
            entity_type="approval_policy",
            entity_id=str(policy.id),
        )

    return policy


async def submit_requisition_for_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
) -> RequisitionApproval:
    """Snapshot the default policy and submit a draft requisition for approval."""
    _require_role(context, _SUBMITTER_ROLES)

    async with transactional(session):
        requisition = await session.scalar(
            select(Requisition)
            .where(
                Requisition.id == requisition_id,
                Requisition.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if requisition is None:
            raise RequisitionNotFoundError("Requisition was not found.")

        if requisition.status is not RequisitionStatus.DRAFT:
            raise ApprovalPolicyInvalidError(
                "Only draft requisitions can be submitted for approval."
            )

        if requisition.created_by_subject != context.subject:
            raise RequisitionAccessDeniedError(
                "Only the person who created this requisition may submit it for approval."
            )

        policy = await session.scalar(
            select(ApprovalPolicy)
            .where(
                ApprovalPolicy.tenant_id == context.tenant_id,
                ApprovalPolicy.is_default.is_(True),
                ApprovalPolicy.is_active.is_(True),
            )
            .with_for_update()
        )
        if policy is None:
            raise ApprovalPolicyNotFoundError(
                "No active default approval policy is configured."
            )

        policy_steps = list(
            await session.scalars(
                select(ApprovalPolicyStep)
                .where(ApprovalPolicyStep.approval_policy_id == policy.id)
                .order_by(ApprovalPolicyStep.position)
            )
        )
        policy_approver_ids = tuple(step.approver_user_id for step in policy_steps)
        admin_approver_ids = await _workspace_admin_user_ids(
            session,
            tenant_id=context.tenant_id,
        )
        approver_ids = tuple(dict.fromkeys((*policy_approver_ids, *admin_approver_ids)))
        approvers = await _tenant_users_by_id(
            session,
            tenant_id=context.tenant_id,
            user_ids=approver_ids,
        )
        eligible_approvers = [
            approvers[user_id]
            for user_id in approver_ids
            if approvers[user_id].external_subject != context.subject
        ]
        if not eligible_approvers:
            raise ApprovalPolicyInvalidError(
                "No eligible approvers remain after excluding the requester. "
                "Contact your workspace admin to add another reviewer."
            )

        policy_snapshot = {
            "policy_id": str(policy.id),
            "policy_name": policy.name,
            "policy_version": policy.version,
            "steps": [
                {
                    "position": 1,
                    "approver_user_id": str(approver.id),
                    "approver_subject": approver.external_subject,
                }
                for approver in eligible_approvers
            ],
            "approval_rule": "any_one_reviewer",
        }

        approval = RequisitionApproval(
            tenant_id=context.tenant_id,
            requisition_id=requisition.id,
            approval_policy_id=policy.id,
            policy_snapshot=policy_snapshot,
            status=ApprovalStatus.PENDING,
            current_step=1,
            submitted_by_subject=context.subject,
        )
        session.add(approval)
        await session.flush()

        session.add_all(
            [
                RequisitionApprovalDecision(
                    requisition_approval_id=approval.id,
                    step_position=1,
                    approver_user_id=approver.id,
                    status=RequisitionDecisionStatus.PENDING,
                )
                for approver in eligible_approvers
            ]
        )

        requisition.status = transition_requisition(
            requisition.status,
            RequisitionStatus.PENDING_APPROVAL,
        )

        record_audit_event(
            session,
            context=context,
            action="requisition.submitted_for_approval",
            entity_type="requisition",
            entity_id=str(requisition.id),
            details={
                "approval_id": str(approval.id),
                "policy_id": str(policy.id),
                "policy_version": policy.version,
            },
        )

    return approval


async def _resolve_actor(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> User:
    """Resolve a verified subject to its tenant-local user record."""
    actor = await session.scalar(
        select(User).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if actor is None:
        raise ApprovalDecisionForbiddenError(
            "Caller is not an assigned approval user."
        )

    return actor


async def list_assigned_requisition_approvals(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> list[tuple[RequisitionApproval, Requisition, RequisitionApprovalDecision]]:
    """List pending requisitions assigned to the authenticated approver."""
    actor = await _resolve_actor(session, context=context)
    rows = await session.execute(
        select(RequisitionApproval, Requisition, RequisitionApprovalDecision)
        .join(
            Requisition,
            Requisition.id == RequisitionApproval.requisition_id,
        )
        .join(
            RequisitionApprovalDecision,
            RequisitionApprovalDecision.requisition_approval_id
            == RequisitionApproval.id,
        )
        .where(
            RequisitionApproval.tenant_id == context.tenant_id,
            Requisition.tenant_id == context.tenant_id,
            RequisitionApproval.status == ApprovalStatus.PENDING,
            RequisitionApprovalDecision.approver_user_id == actor.id,
            RequisitionApprovalDecision.status == RequisitionDecisionStatus.PENDING,
        )
        .order_by(RequisitionApproval.submitted_at.desc())
    )
    return list(rows.tuples())


async def get_assigned_requisition_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    approval_id: UUID,
) -> tuple[RequisitionApproval, Requisition, RequisitionApprovalDecision]:
    """Load approval details only when the caller is on its reviewer chain."""
    actor = await _resolve_actor(session, context=context)
    row = await session.execute(
        select(RequisitionApproval, Requisition, RequisitionApprovalDecision)
        .join(
            Requisition,
            Requisition.id == RequisitionApproval.requisition_id,
        )
        .join(
            RequisitionApprovalDecision,
            RequisitionApprovalDecision.requisition_approval_id
            == RequisitionApproval.id,
        )
        .where(
            RequisitionApproval.id == approval_id,
            RequisitionApproval.tenant_id == context.tenant_id,
            Requisition.tenant_id == context.tenant_id,
            RequisitionApprovalDecision.approver_user_id == actor.id,
        )
    )
    result = row.tuples().first()
    if result is None:
        raise RequisitionApprovalNotFoundError("Approval was not found.")
    return result


async def _load_current_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    approval_id: UUID,
) -> tuple[RequisitionApproval, Requisition, RequisitionApprovalDecision, User]:
    """Lock and return the approval, requisition, pending decision, and actor."""
    approval = await session.scalar(
        select(RequisitionApproval)
        .where(
            RequisitionApproval.id == approval_id,
            RequisitionApproval.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if approval is None:
        raise RequisitionApprovalNotFoundError("Approval was not found.")

    if approval.status is not ApprovalStatus.PENDING:
        raise ApprovalDecisionAlreadyMadeError("Approval is already complete.")

    actor = await _resolve_actor(session, context=context)

    decision = await session.scalar(
        select(RequisitionApprovalDecision)
        .where(
            RequisitionApprovalDecision.requisition_approval_id == approval.id,
            RequisitionApprovalDecision.step_position == approval.current_step,
            RequisitionApprovalDecision.approver_user_id == actor.id,
        )
        .with_for_update()
    )
    if decision is None:
        raise ApprovalDecisionForbiddenError(
            "Caller is not an eligible reviewer for the current approval step."
        )

    if decision.status is not RequisitionDecisionStatus.PENDING:
        raise ApprovalDecisionAlreadyMadeError("Approval decision is already complete.")

    requisition = await session.scalar(
        select(Requisition)
        .where(
            Requisition.id == approval.requisition_id,
            Requisition.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise RequisitionNotFoundError("Requisition was not found.")

    return approval, requisition, decision, actor


async def _mark_alternative_reviewers_not_required(
    session: AsyncSession,
    *,
    approval: RequisitionApproval,
    decision: RequisitionApprovalDecision,
) -> None:
    """Close other reviewers in the winning step after its first decision."""
    await session.execute(
        update(RequisitionApprovalDecision)
        .where(
            RequisitionApprovalDecision.requisition_approval_id == approval.id,
            RequisitionApprovalDecision.step_position == decision.step_position,
            RequisitionApprovalDecision.approver_user_id != decision.approver_user_id,
            RequisitionApprovalDecision.status == RequisitionDecisionStatus.PENDING,
        )
        .values(
            status=RequisitionDecisionStatus.NOT_REQUIRED,
            decided_at=datetime.now(UTC),
        )
    )


async def approve_requisition_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    approval_id: UUID,
    comment: str | None = None,
) -> RequisitionApproval:
    """Approve the current step and advance or approve the requisition."""
    async with transactional(session):
        approval, requisition, decision, actor = await _load_current_approval(
            session,
            context=context,
            approval_id=approval_id,
        )

        decision.status = RequisitionDecisionStatus.APPROVED
        decision.comment = comment
        decision.decided_at = datetime.now(UTC)
        await _mark_alternative_reviewers_not_required(
            session,
            approval=approval,
            decision=decision,
        )

        next_decision = await session.scalar(
            select(RequisitionApprovalDecision)
            .where(
                RequisitionApprovalDecision.requisition_approval_id == approval.id,
                RequisitionApprovalDecision.step_position > approval.current_step,
            )
            .order_by(RequisitionApprovalDecision.step_position)
            .limit(1)
        )

        if next_decision is None:
            approval.status = ApprovalStatus.APPROVED
            approval.completed_at = datetime.now(UTC)
            requisition.status = transition_requisition(
                requisition.status,
                RequisitionStatus.APPROVED,
            )
            action = "requisition_approval.completed"
        else:
            approval.current_step = next_decision.step_position
            action = "requisition_approval.step_approved"

        record_audit_event(
            session,
            context=context,
            action=action,
            entity_type="requisition_approval",
            entity_id=str(approval.id),
            details={
                "approver_user_id": str(actor.id),
                "step_position": decision.step_position,
                "requisition_id": str(requisition.id),
            },
        )

    return approval


async def reject_requisition_approval(
    session: AsyncSession,
    *,
    context: TenantContext,
    approval_id: UUID,
    comment: str | None = None,
) -> RequisitionApproval:
    """Reject the current step and return the requisition to draft."""
    async with transactional(session):
        approval, requisition, decision, actor = await _load_current_approval(
            session,
            context=context,
            approval_id=approval_id,
        )

        decision.status = RequisitionDecisionStatus.REJECTED
        decision.comment = comment
        decision.decided_at = datetime.now(UTC)
        await _mark_alternative_reviewers_not_required(
            session,
            approval=approval,
            decision=decision,
        )

        approval.status = ApprovalStatus.REJECTED
        approval.completed_at = datetime.now(UTC)
        requisition.status = transition_requisition(
            requisition.status,
            RequisitionStatus.DRAFT,
        )

        record_audit_event(
            session,
            context=context,
            action="requisition_approval.rejected",
            entity_type="requisition_approval",
            entity_id=str(approval.id),
            details={
                "approver_user_id": str(actor.id),
                "step_position": decision.step_position,
                "requisition_id": str(requisition.id),
            },
        )

    return approval
