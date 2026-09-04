"""PostgreSQL integration tests for requisition approval services."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.approval import (
    ApprovalPolicy,
    RequisitionApprovalDecision,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant, User
from app.db.models.requisition import Requisition
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.approval_errors import (
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
    SelfApprovalNotAllowedError,
)
from app.services.requisition_approvals import (
    CreateApprovalPolicyCommand,
    approve_requisition_approval,
    create_approval_policy,
    reject_requisition_approval,
    submit_requisition_for_approval,
)
from app.services.requisition_errors import RequisitionAccessDeniedError
from app.services.requisitions import CreateRequisitionCommand, create_requisition


def _context(
    tenant_id: UUID,
    subject: str,
    roles: frozenset[Role],
) -> TenantContext:
    """Build a verified-caller equivalent for approval service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="test-request-id",
    )


async def _create_tenant_and_users(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    subjects: tuple[str, ...],
) -> dict[str, User]:
    """Create a tenant and named users that belong exclusively to it."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )

    users = {
        subject: User(
            tenant_id=tenant_id,
            external_subject=subject,
            email=f"{subject}@example.test",
            display_name=subject.replace("-", " ").title(),
        )
        for subject in subjects
    }
    session.add_all(users.values())
    await session.commit()

    return users


async def _create_requisition_for_submission(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    subject: str,
) -> Requisition:
    """Create one draft requisition using the application service."""
    return await create_requisition(
        session,
        context=_context(
            tenant_id,
            subject,
            frozenset({Role.RECRUITER}),
        ),
        command=CreateRequisitionCommand(
            title="Senior Backend Engineer",
            description=None,
            department="Engineering",
            location="Nairobi",
            headcount=1,
        ),
    )


@pytest.mark.asyncio
async def test_policy_administration_requires_admin_and_replaces_default(
    session: AsyncSession,
) -> None:
    """Require tenant-admin access and keep only one default policy."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("tenant-admin", "approver-one", "approver-two"),
    )

    recruiter_context = _context(
        tenant_id,
        "tenant-admin",
        frozenset({Role.RECRUITER}),
    )
    admin_context = _context(
        tenant_id,
        "tenant-admin",
        frozenset({Role.TENANT_ADMIN}),
    )

    with pytest.raises(RequisitionAccessDeniedError):
        await create_approval_policy(
            session,
            context=recruiter_context,
            command=CreateApprovalPolicyCommand(
                name="Engineering",
                approver_user_ids=(users["approver-one"].id,),
                is_default=True,
            ),
        )

    first_policy = await create_approval_policy(
        session,
        context=admin_context,
        command=CreateApprovalPolicyCommand(
            name="Engineering",
            approver_user_ids=(users["approver-one"].id,),
            is_default=True,
        ),
    )
    second_policy = await create_approval_policy(
        session,
        context=admin_context,
        command=CreateApprovalPolicyCommand(
            name="Finance",
            approver_user_ids=(users["approver-two"].id,),
            is_default=True,
        ),
    )

    policies = list(
        await session.scalars(
            select(ApprovalPolicy).where(ApprovalPolicy.tenant_id == tenant_id)
        )
    )
    default_policy_ids = {policy.id for policy in policies if policy.is_default}

    assert first_policy.id != second_policy.id
    assert default_policy_ids == {second_policy.id}


@pytest.mark.asyncio
async def test_ordered_approvals_approve_requisition_and_record_audit_events(
    session: AsyncSession,
) -> None:
    """Approve sequential policy steps and record the workflow audit events."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter", "approver-one", "approver-two"),
    )

    admin_context = _context(
        tenant_id,
        "recruiter",
        frozenset({Role.TENANT_ADMIN}),
    )
    policy = await create_approval_policy(
        session,
        context=admin_context,
        command=CreateApprovalPolicyCommand(
            name="Default hiring policy",
            approver_user_ids=(
                users["approver-one"].id,
                users["approver-two"].id,
            ),
            is_default=True,
        ),
    )

    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="recruiter",
    )
    approval = await submit_requisition_for_approval(
        session,
        context=_context(
            tenant_id,
            "recruiter",
            frozenset({Role.RECRUITER}),
        ),
        requisition_id=requisition.id,
    )

    first_step = await approve_requisition_approval(
        session,
        context=_context(
            tenant_id,
            "approver-one",
            frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        comment="Approved by hiring manager.",
    )

    assert first_step.status is ApprovalStatus.PENDING
    assert first_step.current_step == 2

    completed = await approve_requisition_approval(
        session,
        context=_context(
            tenant_id,
            "approver-two",
            frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
    )

    stored_requisition = await session.get(Requisition, requisition.id)
    actions = set(
        await session.scalars(
            select(AuditEvent.action).where(
                AuditEvent.entity_id.in_(
                    [
                        str(requisition.id),
                        str(approval.id),
                        str(policy.id),
                    ]
                )
            )
        )
    )

    assert completed.status is ApprovalStatus.APPROVED
    assert completed.completed_at is not None
    assert stored_requisition is not None
    assert stored_requisition.status is RequisitionStatus.APPROVED
    assert "requisition.submitted_for_approval" in actions
    assert "requisition_approval.step_approved" in actions
    assert "requisition_approval.completed" in actions


@pytest.mark.asyncio
async def test_rejection_returns_requisition_to_draft(
    session: AsyncSession,
) -> None:
    """Return a rejected requisition to draft and persist the rejection decision."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter", "approver-one"),
    )

    await create_approval_policy(
        session,
        context=_context(
            tenant_id,
            "recruiter",
            frozenset({Role.TENANT_ADMIN}),
        ),
        command=CreateApprovalPolicyCommand(
            name="Default policy",
            approver_user_ids=(users["approver-one"].id,),
            is_default=True,
        ),
    )

    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="recruiter",
    )
    approval = await submit_requisition_for_approval(
        session,
        context=_context(
            tenant_id,
            "recruiter",
            frozenset({Role.RECRUITER}),
        ),
        requisition_id=requisition.id,
    )

    rejected = await reject_requisition_approval(
        session,
        context=_context(
            tenant_id,
            "approver-one",
            frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        comment="Headcount is not yet approved.",
    )

    stored_requisition = await session.get(Requisition, requisition.id)
    decision = await session.scalar(
        select(RequisitionApprovalDecision).where(
            RequisitionApprovalDecision.requisition_approval_id == approval.id
        )
    )

    assert rejected.status is ApprovalStatus.REJECTED
    assert rejected.completed_at is not None
    assert stored_requisition is not None
    assert stored_requisition.status is RequisitionStatus.DRAFT
    assert decision is not None
    assert decision.status is ApprovalDecisionStatus.REJECTED
    assert decision.comment == "Headcount is not yet approved."


@pytest.mark.asyncio
async def test_submitter_cannot_approve_own_requisition(
    session: AsyncSession,
) -> None:
    """Prevent the requisition submitter from approving their own request."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter",),
    )

    await create_approval_policy(
        session,
        context=_context(
            tenant_id,
            "recruiter",
            frozenset({Role.TENANT_ADMIN}),
        ),
        command=CreateApprovalPolicyCommand(
            name="Unsafe policy",
            approver_user_ids=(users["recruiter"].id,),
            is_default=True,
        ),
    )

    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="recruiter",
    )
    requisition_id = requisition.id

    with pytest.raises(SelfApprovalNotAllowedError):
        await submit_requisition_for_approval(
            session,
            context=_context(
                tenant_id,
                "recruiter",
                frozenset({Role.RECRUITER}),
            ),
            requisition_id=requisition_id,
        )

    stored_requisition = await session.get(Requisition, requisition_id)

    assert stored_requisition is not None
    assert stored_requisition.status is RequisitionStatus.DRAFT


@pytest.mark.asyncio
async def test_hides_approval_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Hide an approval from callers belonging to another tenant."""
    owning_tenant_id = uuid4()
    owning_users = await _create_tenant_and_users(
        session,
        tenant_id=owning_tenant_id,
        subjects=("recruiter", "approver-one"),
    )

    await create_approval_policy(
        session,
        context=_context(
            owning_tenant_id,
            "recruiter",
            frozenset({Role.TENANT_ADMIN}),
        ),
        command=CreateApprovalPolicyCommand(
            name="Default policy",
            approver_user_ids=(owning_users["approver-one"].id,),
            is_default=True,
        ),
    )

    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=owning_tenant_id,
        subject="recruiter",
    )
    approval = await submit_requisition_for_approval(
        session,
        context=_context(
            owning_tenant_id,
            "recruiter",
            frozenset({Role.RECRUITER}),
        ),
        requisition_id=requisition.id,
    )

    other_tenant_id = uuid4()
    await _create_tenant_and_users(
        session,
        tenant_id=other_tenant_id,
        subjects=("other-approver",),
    )

    with pytest.raises(RequisitionApprovalNotFoundError):
        await approve_requisition_approval(
            session,
            context=_context(
                other_tenant_id,
                "other-approver",
                frozenset({Role.HIRING_MANAGER}),
            ),
            approval_id=approval.id,
        )


@pytest.mark.asyncio
async def test_submission_requires_active_default_policy(
    session: AsyncSession,
) -> None:
    """Reject submission when the tenant has no active default policy."""
    tenant_id = uuid4()
    await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter",),
    )

    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="recruiter",
    )

    with pytest.raises(ApprovalPolicyNotFoundError):
        await submit_requisition_for_approval(
            session,
            context=_context(
                tenant_id,
                "recruiter",
                frozenset({Role.RECRUITER}),
            ),
            requisition_id=requisition.id,
        )
