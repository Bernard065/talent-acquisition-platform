"""Transactional policy administration and requisition approval services."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.approval import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    RequisitionApproval,
    RequisitionApprovalDecision,
)
from app.db.models.identity import User
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.requisitions.transitions import transition_requisition
from app.services.approval_errors import (
    ApprovalDecisionAlreadyMadeError,
    ApprovalDecisionForbiddenError,
    ApprovalPolicyInvalidError,
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
    SelfApprovalNotAllowedError,
)
from app.services.audit import record_audit_event
from app.services.requisition_errors import (
    RequisitionAccessDeniedError,
    RequisitionNotFoundError,
)

_POLICY_ADMIN_ROLES = frozenset({Role.TENANT_ADMIN})
_SUBMITTER_ROLES = frozenset({Role.TENANT_ADMIN, Role.RECRUITER})


@dataclass(frozen=True, slots=True)
class CreateApprovalPolicyCommand:
    """Input for a sequential named-approver policy."""

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

        if not self.approver_user_ids:
            raise ApprovalPolicyInvalidError(
                "An approval policy requires at least one approver."
            )

        if len(set(self.approver_user_ids)) != len(self.approver_user_ids):
            raise ApprovalPolicyInvalidError(
                "An approver may appear only once in a policy."
            )


def _require_role(context: TenantContext, allowed_roles: frozenset[Role]) -> None:
    """Enforce service-level authorization without depending on HTTP."""
    if context.roles.isdisjoint(allowed_roles):
        raise RequisitionAccessDeniedError(
            "Caller is not permitted to perform this approval operation."
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


async def create_approval_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateApprovalPolicyCommand,
) -> ApprovalPolicy:
    """Create a tenant approval policy with ordered named approvers."""
    _require_role(context, _POLICY_ADMIN_ROLES)

    async with transactional(session):
        await _tenant_users_by_id(
            session,
            tenant_id=context.tenant_id,
            user_ids=command.approver_user_ids,
        )

        if command.is_default:
            current_default = await session.scalar(
                select(ApprovalPolicy)
                .where(
                    ApprovalPolicy.tenant_id == context.tenant_id,
                    ApprovalPolicy.is_default.is_(True),
                )
                .with_for_update()
            )
            if current_default is not None:
                current_default.is_default = False
                await session.flush()

        policy = ApprovalPolicy(
            tenant_id=context.tenant_id,
            name=command.name.strip(),
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


async def set_default_approval_policy(
    session: AsyncSession,
    *,
    context: TenantContext,
    policy_id: UUID,
) -> ApprovalPolicy:
    """Set one active tenant policy as the default for future submissions."""
    _require_role(context, _POLICY_ADMIN_ROLES)

    async with transactional(session):
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

        steps = list(
            await session.scalars(
                select(ApprovalPolicyStep)
                .where(ApprovalPolicyStep.approval_policy_id == policy.id)
                .order_by(ApprovalPolicyStep.position)
            )
        )
        if not steps:
            raise ApprovalPolicyInvalidError(
                "The default approval policy has no approvers."
            )

        approver_ids = tuple(step.approver_user_id for step in steps)
        approvers = await _tenant_users_by_id(
            session,
            tenant_id=context.tenant_id,
            user_ids=approver_ids,
        )

        if any(user.external_subject == context.subject for user in approvers.values()):
            raise SelfApprovalNotAllowedError(
                "A requisition submitter cannot approve their own requisition."
            )

        policy_snapshot = {
            "policy_id": str(policy.id),
            "policy_name": policy.name,
            "policy_version": policy.version,
            "steps": [
                {
                    "position": step.position,
                    "approver_user_id": str(step.approver_user_id),
                    "approver_subject": approvers[step.approver_user_id].external_subject,
                }
                for step in steps
            ],
        }

        approval = RequisitionApproval(
            tenant_id=context.tenant_id,
            requisition_id=requisition.id,
            approval_policy_id=policy.id,
            policy_snapshot=policy_snapshot,
            status=ApprovalStatus.PENDING,
            current_step=steps[0].position,
            submitted_by_subject=context.subject,
        )
        session.add(approval)
        await session.flush()

        session.add_all(
            [
                RequisitionApprovalDecision(
                    requisition_approval_id=approval.id,
                    step_position=step.position,
                    approver_user_id=step.approver_user_id,
                    status=ApprovalDecisionStatus.PENDING,
                )
                for step in steps
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
        )
        .with_for_update()
    )
    if decision is None:
        raise ApprovalPolicyInvalidError("Approval has no current decision step.")

    if decision.approver_user_id != actor.id:
        raise ApprovalDecisionForbiddenError(
            "Caller is not assigned to the current approval step."
        )

    if decision.status is not ApprovalDecisionStatus.PENDING:
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

        decision.status = ApprovalDecisionStatus.APPROVED
        decision.comment = comment
        decision.decided_at = datetime.now(UTC)

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

        decision.status = ApprovalDecisionStatus.REJECTED
        decision.comment = comment
        decision.decided_at = datetime.now(UTC)

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
