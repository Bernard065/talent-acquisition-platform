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
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.requisition import Requisition
from app.domains.approvals.enums import ApprovalStatus, RequisitionDecisionStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.approval_errors import (
    ApprovalPolicyInvalidError,
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
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
    await session.flush()
    if "tenant-admin" in users:
        session.add(
            UserRoleAssignment(
                user_id=users["tenant-admin"].id,
                role=Role.TENANT_ADMIN,
            )
        )
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
                is_default=False,
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
async def test_recruiter_can_create_only_the_first_default_policy(
    session: AsyncSession,
) -> None:
    """Allow initial setup by recruiters and reserve later changes for admins."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter", "approver-one"),
    )
    recruiter_context = _context(
        tenant_id,
        "recruiter",
        frozenset({Role.RECRUITER}),
    )

    first_policy = await create_approval_policy(
        session,
        context=recruiter_context,
        command=CreateApprovalPolicyCommand(
            name="Initial hiring approval",
            approver_user_ids=(users["approver-one"].id,),
            is_default=True,
        ),
    )

    with pytest.raises(RequisitionAccessDeniedError):
        await create_approval_policy(
            session,
            context=recruiter_context,
            command=CreateApprovalPolicyCommand(
                name="Replacement hiring approval",
                approver_user_ids=(users["approver-one"].id,),
                is_default=True,
            ),
        )

    stored_policy = await session.get(ApprovalPolicy, first_policy.id)
    assert stored_policy is not None
    assert stored_policy.is_default is True


@pytest.mark.asyncio
async def test_only_requisition_creator_can_submit_for_approval(
    session: AsyncSession,
) -> None:
    """Prevent another recruiter from submitting someone else's requisition."""
    tenant_id = uuid4()
    await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("recruiter", "another-recruiter"),
    )
    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="recruiter",
    )
    requisition_id = requisition.id

    with pytest.raises(RequisitionAccessDeniedError):
        await submit_requisition_for_approval(
            session,
            context=_context(
                tenant_id,
                "another-recruiter",
                frozenset({Role.RECRUITER}),
            ),
            requisition_id=requisition_id,
        )


@pytest.mark.asyncio
async def test_any_eligible_reviewer_approves_requisition_and_records_audit_events(
    session: AsyncSession,
) -> None:
    """One selected reviewer completes approval and closes the alternatives."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("tenant-admin", "recruiter", "approver-one", "approver-two"),
    )

    admin_context = _context(
        tenant_id,
        "tenant-admin",
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

    completed = await approve_requisition_approval(
        session,
        context=_context(
            tenant_id,
            "approver-one",
            frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        comment="Approved by hiring manager.",
    )

    stored_requisition = await session.get(Requisition, requisition.id)
    decisions = list(
        await session.scalars(
            select(RequisitionApprovalDecision).where(
                RequisitionApprovalDecision.requisition_approval_id == approval.id
            )
        )
    )
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
    assert completed.current_step == 1
    assert completed.completed_at is not None
    assert stored_requisition is not None
    assert stored_requisition.status is RequisitionStatus.APPROVED
    assert "requisition.submitted_for_approval" in actions
    assert "requisition_approval.completed" in actions
    assert sum(d.status is RequisitionDecisionStatus.APPROVED for d in decisions) == 1
    assert sum(d.status is RequisitionDecisionStatus.NOT_REQUIRED for d in decisions) == 2


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
    assert decision.status is RequisitionDecisionStatus.REJECTED
    assert decision.comment == "Headcount is not yet approved."


@pytest.mark.asyncio
async def test_submitter_is_excluded_and_admin_is_automatic_reviewer(
    session: AsyncSession,
) -> None:
    """Exclude the requester while automatically adding workspace admins."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("tenant-admin", "recruiter"),
    )

    await create_approval_policy(
        session,
        context=_context(
            tenant_id,
            "tenant-admin",
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

    approval = await submit_requisition_for_approval(
        session,
        context=_context(
            tenant_id,
            "recruiter",
            frozenset({Role.RECRUITER}),
        ),
        requisition_id=requisition_id,
    )

    decisions = list(
        await session.scalars(
            select(RequisitionApprovalDecision).where(
                RequisitionApprovalDecision.requisition_approval_id == approval.id
            )
        )
    )

    stored_requisition = await session.get(Requisition, requisition_id)

    assert stored_requisition is not None
    assert stored_requisition.status is RequisitionStatus.PENDING_APPROVAL
    assert [d.approver_user_id for d in decisions] == [users["tenant-admin"].id]
    assert all(d.approver_user_id != users["recruiter"].id for d in decisions)


@pytest.mark.asyncio
async def test_admin_submitter_needs_another_reviewer(
    session: AsyncSession,
) -> None:
    """Block an admin's request when requester exclusion empties the pool."""
    tenant_id = uuid4()
    users = await _create_tenant_and_users(
        session,
        tenant_id=tenant_id,
        subjects=("tenant-admin",),
    )
    await create_approval_policy(
        session,
        context=_context(
            tenant_id,
            "tenant-admin",
            frozenset({Role.TENANT_ADMIN}),
        ),
        command=CreateApprovalPolicyCommand(
            name="Admin-only policy",
            approver_user_ids=(users["tenant-admin"].id,),
            is_default=True,
        ),
    )
    requisition = await _create_requisition_for_submission(
        session,
        tenant_id=tenant_id,
        subject="tenant-admin",
    )

    with pytest.raises(ApprovalPolicyInvalidError, match="add another reviewer"):
        await submit_requisition_for_approval(
            session,
            context=_context(
                tenant_id,
                "tenant-admin",
                frozenset({Role.TENANT_ADMIN}),
            ),
            requisition_id=requisition.id,
        )


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
