"""Workspace offboarding checklist configuration and task operations."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.employee import Employee
from app.db.models.employee_offboarding import (
    EmployeeOffboardingTask,
    EmployeeOffboardingTemplateTask,
)
from app.db.models.identity import Tenant, User
from app.db.transactions import transactional
from app.domains.employees.enums import EmployeeOffboardingTaskStatus, EmployeeStatus
from app.services.audit import record_audit_event
from app.services.onboarding_errors import (
    EmployeeRecordNotFoundError,
    OnboardingAccessDeniedError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)

_OFFBOARDING_ADMIN_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})


@dataclass(frozen=True, slots=True)
class OffboardingTemplateTaskCommand:
    """Validated task definition supplied by a workspace administrator."""

    title: str
    description: str | None
    due_days_before_last_working_day: int


_DEFAULT_TASKS = (
    OffboardingTemplateTaskCommand(
        title="Transfer responsibilities and document handover",
        description="Agree on handover coverage and share outstanding work.",
        due_days_before_last_working_day=3,
    ),
    OffboardingTemplateTaskCommand(
        title="Complete an exit interview",
        description="Capture feedback and any follow-up needed after departure.",
        due_days_before_last_working_day=2,
    ),
    OffboardingTemplateTaskCommand(
        title="Collect company equipment",
        description="Record returned equipment and any items still outstanding.",
        due_days_before_last_working_day=0,
    ),
    OffboardingTemplateTaskCommand(
        title="Confirm final pay and benefits handover",
        description="Coordinate final payroll and benefits information with People Operations.",
        due_days_before_last_working_day=0,
    ),
)


def _require_offboarding_admin(context: TenantContext) -> None:
    if context.roles.isdisjoint(_OFFBOARDING_ADMIN_ROLES):
        raise OnboardingAccessDeniedError(
            "Only workspace admins and People Operations can manage offboarding checklists."
        )


async def list_offboarding_template_tasks(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> list[EmployeeOffboardingTemplateTask]:
    """Return the workspace's ordered offboarding checklist definition."""
    _require_offboarding_admin(context)
    return list(
        await session.scalars(
            select(EmployeeOffboardingTemplateTask)
            .where(EmployeeOffboardingTemplateTask.tenant_id == context.tenant_id)
            .order_by(EmployeeOffboardingTemplateTask.position)
        )
    )


async def replace_offboarding_template_tasks(
    session: AsyncSession,
    *,
    context: TenantContext,
    tasks: tuple[OffboardingTemplateTaskCommand, ...],
) -> list[EmployeeOffboardingTemplateTask]:
    """Replace the workspace task definition for future offboarding plans."""
    _require_offboarding_admin(context)
    if not 1 <= len(tasks) <= 50:
        raise OnboardingValidationError(
            "An offboarding checklist must contain between 1 and 50 tasks."
        )
    if any(not task.title.strip() for task in tasks):
        raise OnboardingValidationError("Every offboarding checklist task needs a title.")

    async with transactional(session):
        await session.scalar(
            select(Tenant.id).where(Tenant.id == context.tenant_id).with_for_update()
        )
        existing_tasks = list(
            await session.scalars(
                select(EmployeeOffboardingTemplateTask)
                .where(EmployeeOffboardingTemplateTask.tenant_id == context.tenant_id)
                .order_by(EmployeeOffboardingTemplateTask.position)
                .with_for_update()
            )
        )
        for task in existing_tasks:
            await session.delete(task)
        await session.flush()

        created_tasks = [
            EmployeeOffboardingTemplateTask(
                tenant_id=context.tenant_id,
                position=position,
                title=task.title.strip(),
                description=task.description.strip() if task.description else None,
                due_days_before_last_working_day=task.due_days_before_last_working_day,
                created_by_subject=context.subject,
            )
            for position, task in enumerate(tasks, start=1)
        ]
        session.add_all(created_tasks)
        record_audit_event(
            session,
            context=context,
            action="employee_offboarding.template_updated",
            entity_type="employee_offboarding_template",
            entity_id=str(context.tenant_id),
            details={"task_count": len(created_tasks)},
        )
        await session.flush()

    return created_tasks


async def create_offboarding_tasks_for_cycle(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee: Employee,
    last_working_day: date,
) -> list[EmployeeOffboardingTask]:
    """Snapshot the configured checklist, or a starter checklist, for a cycle."""
    definitions = list(
        await session.scalars(
            select(EmployeeOffboardingTemplateTask)
            .where(EmployeeOffboardingTemplateTask.tenant_id == context.tenant_id)
            .order_by(EmployeeOffboardingTemplateTask.position)
        )
    )
    cycle_id = uuid4()
    employee.offboarding_cycle_id = cycle_id

    snapshots: list[EmployeeOffboardingTask] = []
    task_specs: list[tuple[UUID | None, int, str, str | None, int]]
    if definitions:
        task_specs = [
            (
                definition.id,
                definition.position,
                definition.title,
                definition.description,
                definition.due_days_before_last_working_day,
            )
            for definition in definitions
        ]
    else:
        task_specs = [
            (None, position, task.title, task.description, task.due_days_before_last_working_day)
            for position, task in enumerate(_DEFAULT_TASKS, start=1)
        ]

    for template_task_id, position, title, description, offset_days in task_specs:
        due_date = last_working_day - timedelta(days=offset_days)
        if employee.start_date is not None and due_date < employee.start_date:
            due_date = employee.start_date
        snapshots.append(
            EmployeeOffboardingTask(
                tenant_id=context.tenant_id,
                employee_id=employee.id,
                offboarding_cycle_id=cycle_id,
                template_task_id=template_task_id,
                position=position,
                title=title,
                description=description,
                due_date=due_date,
            )
        )
    session.add_all(snapshots)
    return snapshots


async def list_employee_offboarding_tasks(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee_id: UUID,
) -> tuple[list[tuple[EmployeeOffboardingTask, str | None]], int, int]:
    """Return the current offboarding cycle and its progress summary."""
    _require_offboarding_admin(context)
    employee = await session.scalar(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == context.tenant_id,
        )
    )
    if employee is None:
        raise EmployeeRecordNotFoundError("Employee record was not found.")
    if employee.status is not EmployeeStatus.OFFBOARDING or employee.offboarding_cycle_id is None:
        return [], 0, 0

    rows = (
        await session.execute(
            select(EmployeeOffboardingTask, User.display_name)
            .outerjoin(
                User,
                (User.id == EmployeeOffboardingTask.assigned_to_user_id)
                & (User.tenant_id == context.tenant_id),
            )
            .where(
                EmployeeOffboardingTask.tenant_id == context.tenant_id,
                EmployeeOffboardingTask.employee_id == employee.id,
                EmployeeOffboardingTask.offboarding_cycle_id == employee.offboarding_cycle_id,
            )
            .order_by(EmployeeOffboardingTask.position)
        )
    ).all()
    tasks = [(task, display_name) for task, display_name in rows]
    completed = sum(task.status is EmployeeOffboardingTaskStatus.COMPLETED for task, _ in tasks)
    return tasks, completed, len(tasks)


async def update_employee_offboarding_task(
    session: AsyncSession,
    *,
    context: TenantContext,
    task_id: UUID,
    expected_version: int,
    changes: dict[str, Any],
) -> EmployeeOffboardingTask:
    """Update task ownership, due date, progress, or completion notes."""
    _require_offboarding_admin(context)
    if not changes or set(changes).difference(
        {"assigned_to_user_id", "due_date", "status", "completion_notes"}
    ):
        raise OnboardingValidationError("At least one valid checklist update is required.")

    async with transactional(session):
        task = await session.scalar(
            select(EmployeeOffboardingTask)
            .where(
                EmployeeOffboardingTask.id == task_id,
                EmployeeOffboardingTask.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if task is None:
            raise EmployeeRecordNotFoundError("Offboarding checklist task was not found.")
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.id == task.employee_id,
                Employee.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if (
            employee is None
            or employee.status is not EmployeeStatus.OFFBOARDING
            or employee.offboarding_cycle_id != task.offboarding_cycle_id
        ):
            raise OnboardingValidationError(
                "This checklist is no longer active because offboarding was cancelled."
            )
        if task.version != expected_version:
            raise OnboardingVersionConflictError(
                "This checklist task changed; reload before saving."
            )

        previous_status = task.status
        if "due_date" in changes and changes["due_date"] is None:
            raise OnboardingValidationError("A checklist task must have a due date.")
        if "status" in changes and changes["status"] is None:
            raise OnboardingValidationError("Choose a checklist task status.")
        next_assignee = changes.get("assigned_to_user_id", task.assigned_to_user_id)
        if next_assignee is not None:
            member_exists = await session.scalar(
                select(User.id).where(
                    User.id == next_assignee,
                    User.tenant_id == context.tenant_id,
                )
            )
            if member_exists is None:
                raise OnboardingValidationError(
                    "Select an existing member of this workspace as the task owner."
                )

        next_due_date = changes.get("due_date", task.due_date)
        if next_due_date is not None and employee.last_working_day is not None:
            if next_due_date > employee.last_working_day:
                raise OnboardingValidationError(
                    "A checklist task cannot be due after the last working day."
                )
            if employee.start_date is not None and next_due_date < employee.start_date:
                raise OnboardingValidationError(
                    "A checklist task cannot be due before the employee's start date."
                )

        for field_name, value in changes.items():
            if field_name == "completion_notes" and isinstance(value, str):
                value = value.strip() or None
            setattr(task, field_name, value)

        if task.status is EmployeeOffboardingTaskStatus.COMPLETED:
            if previous_status is not EmployeeOffboardingTaskStatus.COMPLETED:
                task.completed_at = datetime.now(UTC)
                task.completed_by_subject = context.subject
        elif previous_status is EmployeeOffboardingTaskStatus.COMPLETED:
            task.completed_at = None
            task.completed_by_subject = None

        record_audit_event(
            session,
            context=context,
            action="employee_offboarding.task_updated",
            entity_type="employee_offboarding_task",
            entity_id=str(task.id),
            details={
                "employee_id": str(employee.id),
                "updated_fields": sorted(changes),
                "from_status": previous_status.value,
                "to_status": task.status.value,
                "assigned_to_user_id": (
                    str(task.assigned_to_user_id) if task.assigned_to_user_id is not None else None
                ),
                "due_date": task.due_date.isoformat(),
            },
        )
        await session.flush()
        await session.refresh(task)
    return task
