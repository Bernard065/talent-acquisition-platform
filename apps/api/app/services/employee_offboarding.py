"""Workspace offboarding checklist configuration and task operations."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
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


@dataclass(frozen=True, slots=True)
class EmployeeOffboardingOverviewRow:
    """Employee identity and aggregate progress for an active offboarding cycle."""

    employee: Employee
    employee_name: str
    completed_task_count: int
    total_task_count: int
    overdue_task_count: int
    next_due_date: date | None


@dataclass(frozen=True, slots=True)
class MyEmployeeOffboardingTaskRow:
    """An assigned task with the minimum employee context needed to complete it."""

    task: EmployeeOffboardingTask
    employee_name: str
    job_title: str


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


async def list_employee_offboarding_overview(
    session: AsyncSession,
    *,
    context: TenantContext,
    page: int,
    limit: int,
    query: str | None = None,
    task_status: EmployeeOffboardingTaskStatus | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue_only: bool = False,
) -> tuple[list[EmployeeOffboardingOverviewRow], int]:
    """Return tenant-scoped offboarding cases with task progress summaries."""
    _require_offboarding_admin(context)
    if due_from is not None and due_to is not None and due_from > due_to:
        raise OnboardingValidationError("Task due-from date must not be after due-to date.")

    tenant_id = context.tenant_id
    today = datetime.now(UTC).date()
    task_filters = [
        EmployeeOffboardingTask.tenant_id == tenant_id,
        EmployeeOffboardingTask.employee_id == Employee.id,
        EmployeeOffboardingTask.offboarding_cycle_id == Employee.offboarding_cycle_id,
    ]
    if task_status is not None:
        task_filters.append(EmployeeOffboardingTask.status == task_status)
    if due_from is not None:
        task_filters.append(EmployeeOffboardingTask.due_date >= due_from)
    if due_to is not None:
        task_filters.append(EmployeeOffboardingTask.due_date <= due_to)
    if overdue_only:
        task_filters.extend(
            (
                EmployeeOffboardingTask.due_date < today,
                EmployeeOffboardingTask.status != EmployeeOffboardingTaskStatus.COMPLETED,
            )
        )

    filters = [
        Employee.tenant_id == tenant_id,
        Employee.status == EmployeeStatus.OFFBOARDING,
    ]
    if query and query.strip():
        search_term = f"%{query.strip()}%"
        filters.append(
            or_(
                Candidate.full_name.ilike(search_term),
                Employee.job_title.ilike(search_term),
                Employee.department.ilike(search_term),
                Employee.location.ilike(search_term),
                Employee.employee_number.ilike(search_term),
            )
        )
    if (
        task_status is not None
        or due_from is not None
        or due_to is not None
        or overdue_only
    ):
        filters.append(select(EmployeeOffboardingTask.id).where(*task_filters).exists())

    candidate_join = and_(
        Candidate.id == Employee.candidate_id,
        Candidate.tenant_id == Employee.tenant_id,
    )
    total = await session.scalar(
        select(count(Employee.id))
        .select_from(Employee)
        .join(Candidate, candidate_join)
        .where(*filters)
    )

    task_summary = (
        select(
            EmployeeOffboardingTask.tenant_id.label("tenant_id"),
            EmployeeOffboardingTask.employee_id.label("employee_id"),
            EmployeeOffboardingTask.offboarding_cycle_id.label("cycle_id"),
            count(EmployeeOffboardingTask.id).label("total_task_count"),
            func.sum(
                case(
                    (EmployeeOffboardingTask.status == EmployeeOffboardingTaskStatus.COMPLETED, 1),
                    else_=0,
                )
            ).label("completed_task_count"),
            func.sum(
                case(
                    (
                        and_(
                            EmployeeOffboardingTask.status
                            != EmployeeOffboardingTaskStatus.COMPLETED,
                            EmployeeOffboardingTask.due_date < today,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("overdue_task_count"),
            func.min(
                case(
                    (
                        EmployeeOffboardingTask.status
                        != EmployeeOffboardingTaskStatus.COMPLETED,
                        EmployeeOffboardingTask.due_date,
                    ),
                    else_=None,
                )
            ).label("next_due_date"),
        )
        .where(EmployeeOffboardingTask.tenant_id == tenant_id)
        .group_by(
            EmployeeOffboardingTask.tenant_id,
            EmployeeOffboardingTask.employee_id,
            EmployeeOffboardingTask.offboarding_cycle_id,
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                Employee,
                Candidate.full_name,
                func.coalesce(task_summary.c.completed_task_count, 0),
                func.coalesce(task_summary.c.total_task_count, 0),
                func.coalesce(task_summary.c.overdue_task_count, 0),
                task_summary.c.next_due_date,
            )
            .select_from(Employee)
            .join(Candidate, candidate_join)
            .outerjoin(
                task_summary,
                and_(
                    task_summary.c.tenant_id == Employee.tenant_id,
                    task_summary.c.employee_id == Employee.id,
                    task_summary.c.cycle_id == Employee.offboarding_cycle_id,
                ),
            )
            .where(*filters)
            .order_by(
                Employee.last_working_day.asc().nullslast(),
                Employee.created_at.desc(),
                Employee.id,
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return (
        [
            EmployeeOffboardingOverviewRow(
                employee=employee,
                employee_name=employee_name,
                completed_task_count=int(completed_count),
                total_task_count=int(total_count),
                overdue_task_count=int(overdue_count),
                next_due_date=next_due_date,
            )
            for (
                employee,
                employee_name,
                completed_count,
                total_count,
                overdue_count,
                next_due_date,
            ) in rows
        ],
        total or 0,
    )


async def list_my_employee_offboarding_tasks(
    session: AsyncSession,
    *,
    context: TenantContext,
    page: int,
    limit: int,
    query: str | None = None,
    task_status: EmployeeOffboardingTaskStatus | None = None,
    overdue_only: bool = False,
) -> tuple[list[MyEmployeeOffboardingTaskRow], int]:
    """Return only active-cycle offboarding tasks assigned to this member."""
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user_id is None:
        return [], 0

    today = datetime.now(UTC).date()
    employee_join = and_(
        Employee.id == EmployeeOffboardingTask.employee_id,
        Employee.tenant_id == EmployeeOffboardingTask.tenant_id,
    )
    candidate_join = and_(
        Candidate.id == Employee.candidate_id,
        Candidate.tenant_id == Employee.tenant_id,
    )
    filters = [
        EmployeeOffboardingTask.tenant_id == context.tenant_id,
        EmployeeOffboardingTask.assigned_to_user_id == user_id,
        EmployeeOffboardingTask.offboarding_cycle_id == Employee.offboarding_cycle_id,
        Employee.status == EmployeeStatus.OFFBOARDING,
    ]
    if task_status is not None:
        filters.append(EmployeeOffboardingTask.status == task_status)
    if overdue_only:
        filters.extend(
            (
                EmployeeOffboardingTask.due_date < today,
                EmployeeOffboardingTask.status != EmployeeOffboardingTaskStatus.COMPLETED,
            )
        )
    if query and query.strip():
        search_term = f"%{query.strip()}%"
        filters.append(
            or_(
                EmployeeOffboardingTask.title.ilike(search_term),
                Candidate.full_name.ilike(search_term),
                Employee.job_title.ilike(search_term),
            )
        )

    total = await session.scalar(
        select(count(EmployeeOffboardingTask.id))
        .select_from(EmployeeOffboardingTask)
        .join(Employee, employee_join)
        .join(Candidate, candidate_join)
        .where(*filters)
    )
    rows = (
        await session.execute(
            select(
                EmployeeOffboardingTask,
                Candidate.full_name,
                Employee.job_title,
            )
            .select_from(EmployeeOffboardingTask)
            .join(Employee, employee_join)
            .join(Candidate, candidate_join)
            .where(*filters)
            .order_by(
                EmployeeOffboardingTask.due_date,
                EmployeeOffboardingTask.created_at,
                EmployeeOffboardingTask.id,
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return (
        [
            MyEmployeeOffboardingTaskRow(
                task=task,
                employee_name=employee_name,
                job_title=job_title,
            )
            for task, employee_name, job_title in rows
        ],
        total or 0,
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
    if not changes or set(changes).difference(
        {"assigned_to_user_id", "due_date", "status", "completion_notes"}
    ):
        raise OnboardingValidationError("At least one valid checklist update is required.")
    is_offboarding_admin = not context.roles.isdisjoint(_OFFBOARDING_ADMIN_ROLES)
    owner_editable_fields = {"status", "completion_notes"}
    if not is_offboarding_admin and set(changes).difference(owner_editable_fields):
        raise OnboardingAccessDeniedError(
            "Assigned task owners can update status and completion notes only."
        )

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
        if not is_offboarding_admin:
            current_user_id = await session.scalar(
                select(User.id).where(
                    User.tenant_id == context.tenant_id,
                    User.external_subject == context.subject,
                )
            )
            if current_user_id is None or task.assigned_to_user_id != current_user_id:
                raise EmployeeRecordNotFoundError(
                    "Offboarding checklist task was not found."
                )
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
