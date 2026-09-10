"""PostgreSQL integration tests for the onboarding workflow service."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.onboarding import (
    OnboardingInstanceHistory,
    OnboardingTask,
    OnboardingTaskHistory,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
from app.domains.onboarding.enums import (
    OnboardingInstanceEventType,
    OnboardingInstanceStatus,
    OnboardingTaskEventType,
    OnboardingTaskStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    UpdateOnboardingTaskStatusCommand,
    assign_onboarding_task,
    cancel_onboarding,
    complete_onboarding,
    create_onboarding_template,
    start_onboarding,
    update_onboarding_task_status,
)
from app.services.onboarding_errors import (
    OnboardingAccessDeniedError,
    OnboardingTaskNotFoundError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "people-operations-subject",
    roles: frozenset[Role] = frozenset({Role.PEOPLE_OPERATIONS}),
) -> TenantContext:
    """Build a verified tenant context for service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="onboarding-service-test-request-id",
    )


async def _seed_hired_application(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    application_status: ApplicationStatus = ApplicationStatus.HIRED,
) -> tuple[Application, dict[str, User]]:
    """Create a tenant, operational users, and one application."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Onboarding Tenant {tenant_id.hex[:12]}",
            slug=f"onboarding-{tenant_id.hex[:12]}",
        )
    )

    users = {
        "people-operations-subject": User(
            tenant_id=tenant_id,
            external_subject="people-operations-subject",
            email=f"peopleops-{tenant_id.hex[:12]}@example.test",
            display_name="People Operations",
        ),
        "assignee-subject": User(
            tenant_id=tenant_id,
            external_subject="assignee-subject",
            email=f"assignee-{tenant_id.hex[:12]}@example.test",
            display_name="Task Assignee",
        ),
    }
    session.add_all(users.values())
    await session.flush()
    session.add(
        UserRoleAssignment(
            user_id=users["people-operations-subject"].id,
            role=Role.PEOPLE_OPERATIONS,
        )
    )

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
        source="employee_referral",
        source_metadata={},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="seed",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=application_status,
        created_by_subject="seed",
    )
    session.add(application)
    await session.commit()

    return application, users


async def _create_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    task_count: int = 2,
):
    """Create one versioned onboarding template through the service."""
    tasks = tuple(
        OnboardingTemplateTaskDefinition(
            title=f"Onboarding task {position}",
            description=f"Complete onboarding step {position}.",
            due_offset_days=position,
            default_assignee_role=Role.PEOPLE_OPERATIONS,
        )
        for position in range(1, task_count + 1)
    )

    return await create_onboarding_template(
        session,
        context=_context(tenant_id),
        command=CreateOnboardingTemplateCommand(
            name="Standard employee onboarding",
            tasks=tasks,
        ),
    )


async def _start_onboarding_with_tasks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    task_count: int = 2,
):
    """Seed a hired application, template, and active onboarding instance."""
    application, users = await _seed_hired_application(
        session,
        tenant_id=tenant_id,
    )
    template = await _create_template(
        session,
        tenant_id=tenant_id,
        task_count=task_count,
    )
    instance = await start_onboarding(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        onboarding_template_id=template.id,
    )
    tasks = list(
        await session.scalars(
            select(OnboardingTask)
            .where(OnboardingTask.onboarding_instance_id == instance.id)
            .order_by(OnboardingTask.created_at)
        )
    )
    return application, users, instance, tasks


@pytest.mark.asyncio
async def test_starts_hired_application_with_snapshot_history_and_safe_audit(
    session: AsyncSession,
) -> None:
    """Create task snapshots without copying candidate data into audit events."""
    tenant_id = uuid4()
    application, _ = await _seed_hired_application(
        session,
        tenant_id=tenant_id,
    )
    template = await _create_template(
        session,
        tenant_id=tenant_id,
    )

    instance = await start_onboarding(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        onboarding_template_id=template.id,
    )
    tasks = list(
        await session.scalars(
            select(OnboardingTask).where(
                OnboardingTask.onboarding_instance_id == instance.id
            )
        )
    )
    history = await session.scalar(
        select(OnboardingInstanceHistory).where(
            OnboardingInstanceHistory.onboarding_instance_id == instance.id
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "onboarding.started",
            AuditEvent.entity_id == str(instance.id),
        )
    )

    assert instance.status is OnboardingInstanceStatus.ACTIVE
    assert instance.template_snapshot["template_id"] == str(template.id)
    assert len(instance.template_snapshot["tasks"]) == 2
    assert len(tasks) == 2
    assert tasks[0].due_at == instance.started_at + timedelta(days=1)
    assert history is not None
    assert history.event_type is OnboardingInstanceEventType.STARTED
    assert audit is not None
    assert "candidate_name" not in audit.details
    assert "email" not in audit.details
    assert "description" not in audit.details


@pytest.mark.asyncio
async def test_requires_hired_application_and_authorized_role(
    session: AsyncSession,
) -> None:
    """Prevent onboarding before hire and restrict operational mutations."""
    tenant_id = uuid4()
    application, _ = await _seed_hired_application(
        session,
        tenant_id=tenant_id,
        application_status=ApplicationStatus.OFFER,
    )
    template = await _create_template(
        session,
        tenant_id=tenant_id,
    )

    with pytest.raises(OnboardingValidationError, match="hired"):
        await start_onboarding(
            session,
            context=_context(tenant_id),
            application_id=application.id,
            onboarding_template_id=template.id,
        )

    with pytest.raises(OnboardingAccessDeniedError):
        await create_onboarding_template(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.RECRUITER}),
            ),
            command=CreateOnboardingTemplateCommand(
                name="Unauthorized template",
                tasks=(
                    OnboardingTemplateTaskDefinition(
                        title="Task",
                    ),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_assigns_and_transitions_task_with_history_and_concurrency(
    session: AsyncSession,
) -> None:
    """Assign tenant users and enforce optimistic task updates."""
    tenant_id = uuid4()
    _, users, _, tasks = await _start_onboarding_with_tasks(
        session,
        tenant_id=tenant_id,
        task_count=1,
    )
    task = tasks[0]

    assigned = await assign_onboarding_task(
        session,
        context=_context(tenant_id),
        onboarding_task_id=task.id,
        assignee_user_id=users["assignee-subject"].id,
        expected_task_version=1,
    )
    assert assigned.assignee_user_id == users["assignee-subject"].id
    assert assigned.version == 2

    in_progress = await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=task.id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=2,
            target_status=OnboardingTaskStatus.IN_PROGRESS,
        ),
    )
    assert in_progress.status is OnboardingTaskStatus.IN_PROGRESS
    assert in_progress.version == 3

    blocked = await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=task.id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=3,
            target_status=OnboardingTaskStatus.BLOCKED,
            blocked_reason="Awaiting laptop delivery.",
        ),
    )
    history = list(
        await session.scalars(
            select(OnboardingTaskHistory)
            .where(OnboardingTaskHistory.onboarding_task_id == task.id)
            .order_by(OnboardingTaskHistory.occurred_at)
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "onboarding_task.status_changed",
            AuditEvent.entity_id == str(task.id),
        )
    )

    assert blocked.status is OnboardingTaskStatus.BLOCKED
    assert blocked.blocked_reason == "Awaiting laptop delivery."
    assert history[-1].event_type is OnboardingTaskEventType.BLOCKED
    assert audit is not None
    assert "blocked_reason" not in audit.details

    in_progress = await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=task.id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=4,
            target_status=OnboardingTaskStatus.IN_PROGRESS,
        ),
    )
    completed = await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=task.id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=in_progress.version,
            target_status=OnboardingTaskStatus.COMPLETED,
        ),
    )
    assert completed.status is OnboardingTaskStatus.COMPLETED

    notification_events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "notification.requested",
                OutboxEvent.tenant_id == tenant_id,
            )
        )
    )

    notification_types = {
        event.payload["notification_event_type"]
        for event in notification_events
    }

    assert "onboarding.started" in notification_types
    assert "onboarding.task_assigned" in notification_types
    assert "onboarding.task_blocked" in notification_types
    assert "onboarding.task_completed" in notification_types

    for event in notification_events:
        assert "description" not in event.payload
        assert "blocked_reason" not in event.payload

    with pytest.raises(OnboardingVersionConflictError):
        await update_onboarding_task_status(
            session,
            context=_context(tenant_id),
            onboarding_task_id=task.id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=3,
                target_status=OnboardingTaskStatus.IN_PROGRESS,
            ),
        )


@pytest.mark.asyncio
async def test_prevents_cross_tenant_assignment_and_hides_task(
    session: AsyncSession,
) -> None:
    """Do not permit cross-tenant users or reveal tenant-owned tasks."""
    tenant_id = uuid4()
    _, _, _, tasks = await _start_onboarding_with_tasks(
        session,
        tenant_id=tenant_id,
        task_count=1,
    )
    task_id = tasks[0].id

    other_tenant_id = uuid4()
    _, other_users = await _seed_hired_application(
        session,
        tenant_id=other_tenant_id,
    )

    with pytest.raises(OnboardingValidationError, match="assignee"):
        await assign_onboarding_task(
            session,
            context=_context(tenant_id),
            onboarding_task_id=task_id,
            assignee_user_id=other_users["assignee-subject"].id,
            expected_task_version=1,
        )

    with pytest.raises(OnboardingTaskNotFoundError):
        await update_onboarding_task_status(
            session,
            context=_context(other_tenant_id),
            onboarding_task_id=task_id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=1,
                target_status=OnboardingTaskStatus.IN_PROGRESS,
            ),
        )


@pytest.mark.asyncio
async def test_completes_only_after_all_tasks_are_completed(
    session: AsyncSession,
) -> None:
    """Require every generated task before completing onboarding."""
    tenant_id = uuid4()
    _, _, instance, tasks = await _start_onboarding_with_tasks(
        session,
        tenant_id=tenant_id,
        task_count=2,
    )

    with pytest.raises(OnboardingValidationError, match="All onboarding tasks"):
        await complete_onboarding(
            session,
            context=_context(tenant_id),
            onboarding_instance_id=instance.id,
            expected_instance_version=1,
        )

    for task in tasks:
        in_progress = await update_onboarding_task_status(
            session,
            context=_context(tenant_id),
            onboarding_task_id=task.id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=1,
                target_status=OnboardingTaskStatus.IN_PROGRESS,
            ),
        )
        await update_onboarding_task_status(
            session,
            context=_context(tenant_id),
            onboarding_task_id=task.id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=in_progress.version,
                target_status=OnboardingTaskStatus.COMPLETED,
            ),
        )

    completed = await complete_onboarding(
        session,
        context=_context(tenant_id),
        onboarding_instance_id=instance.id,
        expected_instance_version=1,
    )

    assert completed.status is OnboardingInstanceStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.version == 2


@pytest.mark.asyncio
async def test_cancellation_cancels_non_terminal_tasks_atomically(
    session: AsyncSession,
) -> None:
    """Cancel active onboarding and all incomplete task work together."""
    tenant_id = uuid4()
    _, _, instance, tasks = await _start_onboarding_with_tasks(
        session,
        tenant_id=tenant_id,
        task_count=2,
    )

    in_progress = await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=tasks[0].id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=1,
            target_status=OnboardingTaskStatus.IN_PROGRESS,
        ),
    )
    await update_onboarding_task_status(
        session,
        context=_context(tenant_id),
        onboarding_task_id=tasks[0].id,
        command=UpdateOnboardingTaskStatusCommand(
            expected_version=in_progress.version,
            target_status=OnboardingTaskStatus.COMPLETED,
        ),
    )

    cancelled = await cancel_onboarding(
        session,
        context=_context(tenant_id),
        onboarding_instance_id=instance.id,
        expected_instance_version=1,
    )

    stored_tasks = list(
        await session.scalars(
            select(OnboardingTask)
            .where(OnboardingTask.onboarding_instance_id == instance.id)
            .order_by(OnboardingTask.id)
        )
    )
    instance_history = await session.scalar(
        select(OnboardingInstanceHistory).where(
            OnboardingInstanceHistory.onboarding_instance_id == instance.id,
            OnboardingInstanceHistory.event_type
            == OnboardingInstanceEventType.CANCELLED,
        )
    )

    assert cancelled.status is OnboardingInstanceStatus.CANCELLED
    assert cancelled.cancelled_at is not None
    assert {task.status for task in stored_tasks} == {
        OnboardingTaskStatus.COMPLETED,
        OnboardingTaskStatus.CANCELLED,
    }
    assert instance_history is not None


@pytest.mark.asyncio
async def test_concurrent_task_updates_allow_only_one_current_version(
    database_engine: AsyncEngine,
) -> None:
    """Row locks plus expected versions prevent lost task updates."""
    setup_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    tenant_id = uuid4()

    async with setup_factory() as setup_session:
        _, _, _, tasks = await _start_onboarding_with_tasks(
            setup_session,
            tenant_id=tenant_id,
            task_count=1,
        )
        task_id = tasks[0].id

    worker_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async def update_to(target_status: OnboardingTaskStatus) -> str:
        async with worker_factory() as worker_session:
            try:
                await update_onboarding_task_status(
                    worker_session,
                    context=_context(tenant_id),
                    onboarding_task_id=task_id,
                    command=UpdateOnboardingTaskStatusCommand(
                        expected_version=1,
                        target_status=target_status,
                        blocked_reason=(
                            "Awaiting access."
                            if target_status is OnboardingTaskStatus.BLOCKED
                            else None
                        ),
                    ),
                )
            except OnboardingVersionConflictError:
                return "version_conflict"

            return "updated"

    outcomes = await asyncio.gather(
        update_to(OnboardingTaskStatus.IN_PROGRESS),
        update_to(OnboardingTaskStatus.BLOCKED),
    )

    assert sorted(outcomes) == ["updated", "version_conflict"]
