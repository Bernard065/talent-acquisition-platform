"""Transactional tenant-safe onboarding template, task, and lifecycle services."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.employee import Employee
from app.db.models.identity import User, UserRoleAssignment
from app.db.models.onboarding import (
    OnboardingInstance,
    OnboardingInstanceHistory,
    OnboardingTask,
    OnboardingTaskHistory,
    OnboardingTemplate,
    OnboardingTemplateTask,
)
from app.db.transactions import transactional
from app.domains.candidates.enums import ApplicationStatus
from app.domains.employees.enums import EmployeeStatus
from app.domains.notifications.enums import NotificationEventType
from app.domains.onboarding.enums import (
    OnboardingInstanceEventType,
    OnboardingInstanceStatus,
    OnboardingTaskEventType,
    OnboardingTaskResponsibility,
    OnboardingTaskStatus,
)
from app.domains.onboarding.transitions import (
    validate_instance_transition,
    validate_task_transition,
)
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.employee_records import create_application_employee_record
from app.services.notification_publishing import (
    enqueue_notification_request,
    enqueue_notifications_for_roles,
)
from app.services.onboarding_errors import (
    EmployeePortalRecordNotFoundError,
    OnboardingAccessDeniedError,
    OnboardingAlreadyExistsError,
    OnboardingInstanceNotFoundError,
    OnboardingTaskNotFoundError,
    OnboardingTemplateNotFoundError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)

_TEMPLATE_ADMIN_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.PEOPLE_OPERATIONS,
    }
)
_ONBOARDING_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.PEOPLE_OPERATIONS,
        Role.RECRUITER,
    }
)
_MAX_NAME_LENGTH = 200
_MAX_DESCRIPTION_LENGTH = 5_000
_MAX_BLOCK_REASON_LENGTH = 2_000


async def list_onboarding_overview(
    session: AsyncSession,
    *,
    context: TenantContext,
    page: int,
    limit: int,
    query: str | None = None,
    status: OnboardingInstanceStatus | None = None,
    overdue_only: bool = False,
) -> tuple[
    list[tuple[OnboardingInstance, str, str, int, int, int]],
    int,
    int,
    int,
]:
    """List matching tenant onboarding plans and workspace-wide counters."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    filters: list[ColumnElement[bool]] = [
        OnboardingInstance.tenant_id == context.tenant_id,
    ]
    if status is not None:
        filters.append(OnboardingInstance.status == status)
    if query and query.strip():
        search_term = f"%{query.strip()}%"
        filters.append(
            or_(
                Candidate.full_name.ilike(search_term),
                Employee.job_title.ilike(search_term),
            )
        )
    if overdue_only:
        filters.append(
            exists(
                select(OnboardingTask.id).where(
                    OnboardingTask.tenant_id == OnboardingInstance.tenant_id,
                    OnboardingTask.onboarding_instance_id == OnboardingInstance.id,
                    OnboardingTask.due_at < func.current_timestamp(),
                    OnboardingTask.status.not_in(
                        {
                            OnboardingTaskStatus.COMPLETED,
                            OnboardingTaskStatus.CANCELLED,
                        }
                    ),
                )
            )
        )

    application_join = and_(
        Application.id == OnboardingInstance.application_id,
        Application.tenant_id == OnboardingInstance.tenant_id,
    )
    candidate_join = and_(
        Candidate.id == Application.candidate_id,
        Candidate.tenant_id == Application.tenant_id,
    )
    employee_join = and_(
        Employee.application_id == Application.id,
        Employee.tenant_id == Application.tenant_id,
    )
    joins = (
        select(OnboardingInstance, Candidate.full_name, Employee.job_title)
        .join(Application, application_join)
        .join(Candidate, candidate_join)
        .join(Employee, employee_join)
    )
    total = await session.scalar(
        select(func.count(OnboardingInstance.id))
        .select_from(OnboardingInstance)
        .join(Application, application_join)
        .join(Candidate, candidate_join)
        .join(Employee, employee_join)
        .where(*filters)
    )
    rows = await session.execute(
        joins.where(*filters)
        .order_by(OnboardingInstance.started_at.desc(), OnboardingInstance.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    plans = list(rows.tuples())

    instance_ids = [instance.id for instance, _, _ in plans]
    tasks_by_instance: dict[UUID, list[OnboardingTask]] = {
        instance_id: [] for instance_id in instance_ids
    }
    if instance_ids:
        tasks = await session.scalars(
            select(OnboardingTask).where(
                OnboardingTask.tenant_id == context.tenant_id,
                OnboardingTask.onboarding_instance_id.in_(instance_ids),
            )
        )
        for task in tasks:
            tasks_by_instance[task.onboarding_instance_id].append(task)

    now = datetime.now(UTC)
    items = []
    for instance, employee_name, job_title in plans:
        instance_tasks = tasks_by_instance[instance.id]
        items.append(
            (
                instance,
                employee_name,
                job_title,
                len(instance_tasks),
                sum(
                    task.status is OnboardingTaskStatus.COMPLETED
                    for task in instance_tasks
                ),
                sum(
                    task.due_at is not None
                    and task.due_at < now
                    and task.status
                    not in {
                        OnboardingTaskStatus.COMPLETED,
                        OnboardingTaskStatus.CANCELLED,
                    }
                    for task in instance_tasks
                ),
            )
        )

    active_count = await session.scalar(
        select(func.count(OnboardingInstance.id)).where(
            OnboardingInstance.tenant_id == context.tenant_id,
            OnboardingInstance.status == OnboardingInstanceStatus.ACTIVE,
        )
    )
    overdue_count = await session.scalar(
        select(func.count(OnboardingTask.id))
        .join(
            OnboardingInstance,
            and_(
                OnboardingInstance.id == OnboardingTask.onboarding_instance_id,
                OnboardingInstance.tenant_id == OnboardingTask.tenant_id,
            ),
        )
        .where(
            OnboardingTask.tenant_id == context.tenant_id,
            OnboardingInstance.status == OnboardingInstanceStatus.ACTIVE,
            OnboardingTask.due_at < func.current_timestamp(),
            OnboardingTask.status.not_in(
                {
                    OnboardingTaskStatus.COMPLETED,
                    OnboardingTaskStatus.CANCELLED,
                }
            ),
        )
    )
    return items, total or 0, active_count or 0, overdue_count or 0


async def list_active_onboarding_templates(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> list[tuple[OnboardingTemplate, tuple[OnboardingTemplateTask, ...]]]:
    """List active tenant templates and their ordered task definitions."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    templates = list(
        await session.scalars(
            select(OnboardingTemplate)
            .where(
                OnboardingTemplate.tenant_id == context.tenant_id,
                OnboardingTemplate.is_active.is_(True),
            )
            .order_by(
                OnboardingTemplate.name,
                OnboardingTemplate.version.desc(),
            )
        )
    )
    if not templates:
        return []

    task_rows = await session.execute(
        select(OnboardingTemplateTask)
        .where(
            OnboardingTemplateTask.onboarding_template_id.in_(
                template.id for template in templates
            )
        )
        .order_by(
            OnboardingTemplateTask.onboarding_template_id,
            OnboardingTemplateTask.position,
        )
    )
    tasks_by_template: dict[UUID, list[OnboardingTemplateTask]] = {}
    for task in task_rows.scalars():
        tasks_by_template.setdefault(task.onboarding_template_id, []).append(task)

    return [
        (template, tuple(tasks_by_template.get(template.id, ())))
        for template in templates
    ]


async def get_application_onboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> tuple[OnboardingInstance, tuple[OnboardingTask, ...]] | None:
    """Load onboarding state for one tenant application without candidate PII."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    application = await session.scalar(
        select(Application.id).where(
            Application.id == application_id,
            Application.tenant_id == context.tenant_id,
        )
    )
    if application is None:
        raise ApplicationNotFoundError("Application was not found.")

    instance = await session.scalar(
        select(OnboardingInstance).where(
            OnboardingInstance.tenant_id == context.tenant_id,
            OnboardingInstance.application_id == application_id,
        )
    )
    if instance is None:
        return None

    tasks = tuple(
        await session.scalars(
            select(OnboardingTask)
            .join(
                OnboardingTemplateTask,
                OnboardingTask.template_task_id == OnboardingTemplateTask.id,
            )
            .where(
                OnboardingTask.tenant_id == context.tenant_id,
                OnboardingTask.onboarding_instance_id == instance.id,
            )
            .order_by(OnboardingTemplateTask.position, OnboardingTask.id)
        )
    )
    return instance, tasks


async def _get_employee_for_subject(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> tuple[Employee, str]:
    """Resolve an active employee profile from the verified tenant subject."""
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user_id is None:
        raise EmployeePortalRecordNotFoundError("Employee record was not found.")

    employee_result = await session.execute(
        select(Employee, Candidate.full_name)
        .join(
            Candidate,
            and_(
                Candidate.id == Employee.candidate_id,
                Candidate.tenant_id == Employee.tenant_id,
            ),
        )
        .where(
            Employee.tenant_id == context.tenant_id,
            Employee.user_id == user_id,
        )
    )
    employee_row = employee_result.one_or_none()
    if employee_row is None:
        raise EmployeePortalRecordNotFoundError("Employee record was not found.")
    employee, full_name = employee_row
    if employee.status is EmployeeStatus.INACTIVE:
        raise EmployeePortalRecordNotFoundError("Employee record was not found.")

    return employee, full_name


async def get_employee_portal_onboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> tuple[
    Employee,
    str,
    OnboardingInstance | None,
    tuple[OnboardingTask, ...],
]:
    """Return onboarding only for the employee linked to the verified subject."""
    employee, full_name = await _get_employee_for_subject(
        session,
        context=context,
    )

    instance = await session.scalar(
        select(OnboardingInstance).where(
            OnboardingInstance.tenant_id == context.tenant_id,
            OnboardingInstance.application_id == employee.application_id,
        )
    )
    tasks: tuple[OnboardingTask, ...] = ()
    if instance is not None:
        tasks = tuple(
            await session.scalars(
                select(OnboardingTask)
                .join(
                    OnboardingTemplateTask,
                    OnboardingTask.template_task_id == OnboardingTemplateTask.id,
                )
                .where(
                    OnboardingTask.tenant_id == context.tenant_id,
                    OnboardingTask.onboarding_instance_id == instance.id,
                )
                .order_by(OnboardingTemplateTask.position, OnboardingTask.id)
            )
        )

    return employee, full_name, instance, tasks


@dataclass(frozen=True, slots=True)
class OnboardingTemplateTaskDefinition:
    """One ordered task definition for an onboarding template."""

    title: str
    description: str | None = None
    due_offset_days: int | None = None
    default_assignee_role: Role | None = None
    responsible_party: OnboardingTaskResponsibility = (
        OnboardingTaskResponsibility.WORKSPACE
    )

    def __post_init__(self) -> None:
        normalized_title = self.title.strip()
        normalized_description = (
            self.description.strip() if self.description is not None else None
        )

        if not normalized_title:
            raise OnboardingValidationError("Template task title is required.")

        if len(normalized_title) > _MAX_NAME_LENGTH:
            raise OnboardingValidationError(
                "Template task title must not exceed 200 characters."
            )

        if normalized_description == "":
            normalized_description = None

        if (
            normalized_description is not None
            and len(normalized_description) > _MAX_DESCRIPTION_LENGTH
        ):
            raise OnboardingValidationError(
                "Template task description must not exceed 5000 characters."
            )

        if self.due_offset_days is not None and self.due_offset_days < 0:
            raise OnboardingValidationError(
                "Template task due offset cannot be negative."
            )

        if (
            self.responsible_party is OnboardingTaskResponsibility.EMPLOYEE
            and self.default_assignee_role is not None
        ):
            raise OnboardingValidationError(
                "Employee-owned tasks cannot have a default workspace assignee role."
            )

        object.__setattr__(self, "title", normalized_title)
        object.__setattr__(self, "description", normalized_description)


@dataclass(frozen=True, slots=True)
class CreateOnboardingTemplateCommand:
    """Input for an immutable versioned onboarding template definition."""

    name: str
    tasks: tuple[OnboardingTemplateTaskDefinition, ...]
    version: int = 1

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise OnboardingValidationError("Template name is required.")

        if len(normalized_name) > _MAX_NAME_LENGTH:
            raise OnboardingValidationError(
                "Template name must not exceed 200 characters."
            )

        if self.version < 1:
            raise OnboardingValidationError(
                "Template version must be at least one."
            )

        if not self.tasks:
            raise OnboardingValidationError(
                "An onboarding template requires at least one task."
            )

        object.__setattr__(self, "name", normalized_name)


@dataclass(frozen=True, slots=True)
class UpdateOnboardingTaskStatusCommand:
    """Input for one optimistic-concurrency task lifecycle transition."""

    expected_version: int
    target_status: OnboardingTaskStatus
    blocked_reason: str | None = None
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        normalized_reason = (
            self.blocked_reason.strip()
            if self.blocked_reason is not None
            else None
        )
        normalized_resolution_note = (
            self.resolution_note.strip()
            if self.resolution_note is not None
            else None
        )

        if self.expected_version < 1:
            raise OnboardingValidationError(
                "Expected task version must be at least one."
            )

        if self.target_status is OnboardingTaskStatus.BLOCKED:
            if not normalized_reason:
                raise OnboardingValidationError(
                    "A blocked task requires a blocked reason."
                )
        elif normalized_reason is not None:
            raise OnboardingValidationError(
                "A blocked reason is allowed only when a task is blocked."
            )

        if (
            normalized_resolution_note is not None
            and self.target_status is not OnboardingTaskStatus.IN_PROGRESS
        ):
            raise OnboardingValidationError(
                "A resolution note is allowed only when reopening a task."
            )

        if (
            normalized_reason is not None
            and len(normalized_reason) > _MAX_BLOCK_REASON_LENGTH
        ):
            raise OnboardingValidationError(
                "Blocked reason must not exceed 2000 characters."
            )

        if (
            normalized_resolution_note is not None
            and len(normalized_resolution_note) > _MAX_BLOCK_REASON_LENGTH
        ):
            raise OnboardingValidationError(
                "Resolution note must not exceed 2000 characters."
            )

        object.__setattr__(self, "blocked_reason", normalized_reason)
        object.__setattr__(self, "resolution_note", normalized_resolution_note)


def _require_role(
    context: TenantContext,
    allowed_roles: frozenset[Role],
) -> None:
    """Enforce authorization at the application-service boundary."""
    if context.roles.isdisjoint(allowed_roles):
        raise OnboardingAccessDeniedError(
            "Caller is not permitted to perform this onboarding operation."
        )


def _validate_version(
    *,
    actual_version: int,
    expected_version: int,
    entity_name: str,
) -> None:
    """Reject stale writes before mutation."""
    if expected_version < 1:
        raise OnboardingValidationError(
            f"Expected {entity_name} version must be at least one."
        )

    if actual_version != expected_version:
        raise OnboardingVersionConflictError(
            f"{entity_name.capitalize()} has changed since the supplied version."
        )


def _append_instance_history(
    session: AsyncSession,
    *,
    context: TenantContext,
    instance: OnboardingInstance,
    event_type: OnboardingInstanceEventType,
    from_status: OnboardingInstanceStatus | None,
    to_status: OnboardingInstanceStatus,
) -> None:
    """Append immutable onboarding instance history."""
    session.add(
        OnboardingInstanceHistory(
            tenant_id=context.tenant_id,
            onboarding_instance_id=instance.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            occurred_by_subject=context.subject,
        )
    )


def _append_task_history(
    session: AsyncSession,
    *,
    context: TenantContext,
    task: OnboardingTask,
    event_type: OnboardingTaskEventType,
    from_status: OnboardingTaskStatus | None,
    to_status: OnboardingTaskStatus,
    note: str | None = None,
) -> None:
    """Append immutable onboarding task history."""
    session.add(
        OnboardingTaskHistory(
            tenant_id=context.tenant_id,
            onboarding_task_id=task.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            note=note,
            occurred_by_subject=context.subject,
        )
    )


async def create_onboarding_template(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateOnboardingTemplateCommand,
) -> OnboardingTemplate:
    """Create one tenant-owned immutable template version."""
    _require_role(context, _TEMPLATE_ADMIN_ROLES)

    async with transactional(session):
        template = OnboardingTemplate(
            tenant_id=context.tenant_id,
            name=command.name,
            version=command.version,
            is_active=True,
            created_by_subject=context.subject,
        )
        session.add(template)
        await session.flush()

        session.add_all(
            [
                OnboardingTemplateTask(
                    onboarding_template_id=template.id,
                    position=position,
                    title=task.title,
                    description=task.description,
                    due_offset_days=task.due_offset_days,
                    default_assignee_role=task.default_assignee_role,
                    responsible_party=task.responsible_party,
                )
                for position, task in enumerate(command.tasks, start=1)
            ]
        )

        record_audit_event(
            session,
            context=context,
            action="onboarding_template.created",
            entity_type="onboarding_template",
            entity_id=str(template.id),
            details={
                "version": template.version,
                "task_count": len(command.tasks),
            },
        )

        await session.flush()
        await session.refresh(template)

    return template


async def start_onboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    onboarding_template_id: UUID,
) -> OnboardingInstance:
    """Instantiate an active template only for a hired application."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    async with transactional(session):
        application = await session.scalar(
            select(Application)
            .where(
                Application.id == application_id,
                Application.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if application is None:
            raise ApplicationNotFoundError("Application was not found.")

        if application.status is not ApplicationStatus.HIRED:
            raise OnboardingValidationError(
                "Only hired applications can begin onboarding."
            )

        existing_instance = await session.scalar(
            select(OnboardingInstance.id).where(
                OnboardingInstance.tenant_id == context.tenant_id,
                OnboardingInstance.application_id == application.id,
            )
        )
        if existing_instance is not None:
            raise OnboardingAlreadyExistsError(
                "This application already has an onboarding instance."
            )

        template = await session.scalar(
            select(OnboardingTemplate)
            .where(
                OnboardingTemplate.id == onboarding_template_id,
                OnboardingTemplate.tenant_id == context.tenant_id,
                OnboardingTemplate.is_active.is_(True),
            )
            .with_for_update()
        )
        if template is None:
            raise OnboardingTemplateNotFoundError(
                "Active onboarding template was not found."
            )

        template_tasks = list(
            await session.scalars(
                select(OnboardingTemplateTask)
                .where(
                    OnboardingTemplateTask.onboarding_template_id == template.id
                )
                .order_by(OnboardingTemplateTask.position)
            )
        )
        if not template_tasks:
            raise OnboardingValidationError(
                "An onboarding template must contain at least one task."
            )

        started_at = datetime.now(UTC)
        requested_roles = {
            task.default_assignee_role
            for task in template_tasks
            if task.default_assignee_role is not None
        }
        users_by_role: dict[Role, list[UUID]] = {}
        if requested_roles:
            role_rows = await session.execute(
                select(UserRoleAssignment.role, User.id)
                .join(User, User.id == UserRoleAssignment.user_id)
                .where(
                    User.tenant_id == context.tenant_id,
                    UserRoleAssignment.role.in_(requested_roles),
                )
                .order_by(User.display_name, User.id)
            )
            for role, user_id in role_rows:
                users_by_role.setdefault(role, []).append(user_id)

        template_snapshot = {
            "template_id": str(template.id),
            "template_name": template.name,
            "template_version": template.version,
            "tasks": [
                {
                    "template_task_id": str(task.id),
                    "position": task.position,
                    "title": task.title,
                    "description": task.description,
                    "due_offset_days": task.due_offset_days,
                    "default_assignee_role": (
                        task.default_assignee_role.value
                        if task.default_assignee_role is not None
                        else None
                    ),
                    "responsible_party": task.responsible_party.value,
                }
                for task in template_tasks
            ],
        }

        instance = OnboardingInstance(
            tenant_id=context.tenant_id,
            application_id=application.id,
            onboarding_template_id=template.id,
            template_snapshot=template_snapshot,
            status=OnboardingInstanceStatus.ACTIVE,
            started_by_subject=context.subject,
            started_at=started_at,
        )
        session.add(instance)
        await session.flush()

        tasks = [
            OnboardingTask(
                tenant_id=context.tenant_id,
                onboarding_instance_id=instance.id,
                template_task_id=template_task.id,
                title=template_task.title,
                description=template_task.description,
                due_at=(
                    started_at + timedelta(days=template_task.due_offset_days)
                    if template_task.due_offset_days is not None
                    else None
                ),
                responsible_party=template_task.responsible_party,
                status=OnboardingTaskStatus.NOT_STARTED,
                assignee_user_id=(
                    users_by_role[template_task.default_assignee_role][0]
                    if template_task.default_assignee_role is not None
                    and len(users_by_role.get(template_task.default_assignee_role, ()))
                    == 1
                    else None
                ),
            )
            for template_task in template_tasks
        ]
        session.add_all(tasks)

        _append_instance_history(
            session,
            context=context,
            instance=instance,
            event_type=OnboardingInstanceEventType.STARTED,
            from_status=None,
            to_status=OnboardingInstanceStatus.ACTIVE,
        )
        record_audit_event(
            session,
            context=context,
            action="onboarding.started",
            entity_type="onboarding_instance",
            entity_id=str(instance.id),
            details={
                "application_id": str(application.id),
                "template_id": str(template.id),
                "template_version": template.version,
                "task_count": len(tasks),
            },
        )
        employee_record_id = await session.scalar(
            select(Employee.id).where(
                Employee.tenant_id == context.tenant_id,
                Employee.application_id == application.id,
            )
        )
        if employee_record_id is None:
            await create_application_employee_record(
                session,
                context=context,
                application_id=application.id,
                employee_number=None,
                work_email=None,
                start_date=None,
                manager_user_id=None,
            )
        await enqueue_notifications_for_roles(
            session,
            context=context,
            roles=(Role.PEOPLE_OPERATIONS,),
            notification_event_type=NotificationEventType.ONBOARDING_STARTED,
            entity_type="onboarding_instance",
            entity_id=instance.id,
            template_key="onboarding_started",
        )

        await session.flush()
        await session.refresh(instance)

    return instance


async def _load_active_task(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
) -> tuple[OnboardingTask, OnboardingInstance]:
    """Load a task and its parent instance under locks."""
    task = await session.scalar(
        select(OnboardingTask)
        .where(
            OnboardingTask.id == onboarding_task_id,
            OnboardingTask.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if task is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")

    instance = await session.scalar(
        select(OnboardingInstance)
        .where(
            OnboardingInstance.id == task.onboarding_instance_id,
            OnboardingInstance.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if instance is None:
        raise OnboardingInstanceNotFoundError(
            "Onboarding instance was not found."
        )

    if instance.status is not OnboardingInstanceStatus.ACTIVE:
        raise OnboardingValidationError(
            "Tasks can be changed only while onboarding is active."
        )

    return task, instance


async def _require_task_predecessors_complete(
    session: AsyncSession,
    *,
    context: TenantContext,
    task: OnboardingTask,
) -> None:
    """Prevent work on a task until every earlier template step is complete."""
    template_task = await session.scalar(
        select(OnboardingTemplateTask)
        .join(
            OnboardingTemplate,
            OnboardingTemplateTask.onboarding_template_id == OnboardingTemplate.id,
        )
        .where(
            OnboardingTemplateTask.id == task.template_task_id,
            OnboardingTemplate.tenant_id == context.tenant_id,
        )
    )
    if template_task is None:
        raise OnboardingValidationError(
            "This onboarding task is not linked to a valid template step."
        )

    blocking_task = await session.scalar(
        select(OnboardingTask)
        .join(
            OnboardingTemplateTask,
            OnboardingTask.template_task_id == OnboardingTemplateTask.id,
        )
        .where(
            OnboardingTask.tenant_id == context.tenant_id,
            OnboardingTask.onboarding_instance_id == task.onboarding_instance_id,
            OnboardingTemplateTask.onboarding_template_id
            == template_task.onboarding_template_id,
            OnboardingTemplateTask.position < template_task.position,
            OnboardingTask.status != OnboardingTaskStatus.COMPLETED,
        )
        .order_by(OnboardingTemplateTask.position)
        .limit(1)
    )
    if blocking_task is not None:
        raise OnboardingValidationError(
            "Complete the earlier onboarding tasks before changing this task."
        )


async def assign_onboarding_task(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
    assignee_user_id: UUID,
    expected_task_version: int,
) -> OnboardingTask:
    """Assign an active task to a user belonging to the same tenant."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    async with transactional(session):
        task, _ = await _load_active_task(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
        )
        _validate_version(
            actual_version=task.version,
            expected_version=expected_task_version,
            entity_name="onboarding task",
        )
        await _require_task_predecessors_complete(
            session,
            context=context,
            task=task,
        )

        if task.responsible_party is OnboardingTaskResponsibility.EMPLOYEE:
            raise OnboardingValidationError(
                "Employee-owned tasks cannot be assigned to workspace members."
            )

        if task.status in {
            OnboardingTaskStatus.COMPLETED,
            OnboardingTaskStatus.CANCELLED,
        }:
            raise OnboardingValidationError(
                "Terminal onboarding tasks cannot be reassigned."
            )

        assignee = await session.scalar(
            select(User).where(
                User.id == assignee_user_id,
                User.tenant_id == context.tenant_id,
            )
        )
        if assignee is None:
            raise OnboardingValidationError(
                "Task assignee must belong to the tenant."
            )

        task.assignee_user_id = assignee.id

        _append_task_history(
            session,
            context=context,
            task=task,
            event_type=OnboardingTaskEventType.ASSIGNED,
            from_status=task.status,
            to_status=task.status,
        )
        record_audit_event(
            session,
            context=context,
            action="onboarding_task.assigned",
            entity_type="onboarding_task",
            entity_id=str(task.id),
            details={
                "assignee_user_id": str(assignee.id),
            },
        )
        enqueue_notification_request(
            session,
            context=context,
            recipient_user_id=assignee.id,
            notification_event_type=NotificationEventType.ONBOARDING_TASK_ASSIGNED,
            entity_type="onboarding_task",
            entity_id=task.id,
            template_key="onboarding_task_assigned",
        )

        await session.flush()
        await session.refresh(task)

    return task


async def _apply_onboarding_task_status_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    task: OnboardingTask,
    command: UpdateOnboardingTaskStatusCommand,
) -> OnboardingTask:
    """Apply shared task transition, audit, and notification behavior."""
    _validate_version(
        actual_version=task.version,
        expected_version=command.expected_version,
        entity_name="onboarding task",
    )
    await _require_task_predecessors_complete(
        session,
        context=context,
        task=task,
    )

    previous_status = task.status
    validate_task_transition(previous_status, command.target_status)
    task.status = command.target_status
    history_note: str | None = None

    if command.target_status is OnboardingTaskStatus.COMPLETED:
        task.completed_at = datetime.now(UTC)
        task.blocked_reason = None
        event_type = OnboardingTaskEventType.COMPLETED
    elif command.target_status is OnboardingTaskStatus.BLOCKED:
        task.completed_at = None
        task.blocked_reason = command.blocked_reason
        task.resolution_note = None
        history_note = command.blocked_reason
        event_type = OnboardingTaskEventType.BLOCKED
    elif command.target_status is OnboardingTaskStatus.CANCELLED:
        task.completed_at = None
        task.blocked_reason = None
        event_type = OnboardingTaskEventType.CANCELLED
    else:
        task.completed_at = None
        task.blocked_reason = None
        if previous_status is OnboardingTaskStatus.BLOCKED:
            task.resolution_note = command.resolution_note
            history_note = command.resolution_note
        event_type = OnboardingTaskEventType.STATUS_CHANGED

    _append_task_history(
        session,
        context=context,
        task=task,
        event_type=event_type,
        from_status=previous_status,
        to_status=task.status,
        note=history_note,
    )
    record_audit_event(
        session,
        context=context,
        action="onboarding_task.status_changed",
        entity_type="onboarding_task",
        entity_id=str(task.id),
        details={
            "from_status": previous_status.value,
            "to_status": task.status.value,
        },
    )
    if event_type in {
        OnboardingTaskEventType.BLOCKED,
        OnboardingTaskEventType.COMPLETED,
    }:
        notification_event_type = (
            NotificationEventType.ONBOARDING_TASK_BLOCKED
            if event_type is OnboardingTaskEventType.BLOCKED
            else NotificationEventType.ONBOARDING_TASK_COMPLETED
        )
        template_key = (
            "onboarding_task_blocked"
            if event_type is OnboardingTaskEventType.BLOCKED
            else "onboarding_task_completed"
        )
        await enqueue_notifications_for_roles(
            session,
            context=context,
            roles=(Role.PEOPLE_OPERATIONS,),
            notification_event_type=notification_event_type,
            entity_type="onboarding_task",
            entity_id=task.id,
            template_key=template_key,
        )

    await session.flush()
    await session.refresh(task)
    return task


async def update_onboarding_task_status(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
    command: UpdateOnboardingTaskStatusCommand,
) -> OnboardingTask:
    """Transition one active workspace task and record immutable history."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    async with transactional(session):
        task, instance = await _load_active_task(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
        )
        resolves_employee_blocker = (
            task.responsible_party is OnboardingTaskResponsibility.EMPLOYEE
            and task.status is OnboardingTaskStatus.BLOCKED
            and command.target_status is OnboardingTaskStatus.IN_PROGRESS
        )
        if resolves_employee_blocker and not command.resolution_note:
            raise OnboardingValidationError(
                "Add a response for the employee before reopening this task."
            )
        if command.resolution_note is not None and not resolves_employee_blocker:
            raise OnboardingValidationError(
                "A response can be added only when resolving an employee blocker."
            )

        await _apply_onboarding_task_status_update(
            session,
            context=context,
            task=task,
            command=command,
        )
        if resolves_employee_blocker:
            employee_user_id = await session.scalar(
                select(Employee.user_id).where(
                    Employee.tenant_id == context.tenant_id,
                    Employee.application_id == instance.application_id,
                )
            )
            if employee_user_id is not None:
                enqueue_notification_request(
                    session,
                    context=context,
                    recipient_user_id=employee_user_id,
                    notification_event_type=(
                        NotificationEventType.ONBOARDING_TASK_UNBLOCKED
                    ),
                    entity_type="onboarding_task",
                    entity_id=task.id,
                    template_key="onboarding_task_unblocked",
                    occurrence_key=task.version,
                )

    return task


async def update_employee_portal_task_status(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
    command: UpdateOnboardingTaskStatusCommand,
) -> OnboardingTask:
    """Allow an employee to progress or request help for their own task."""
    if command.target_status not in {
        OnboardingTaskStatus.IN_PROGRESS,
        OnboardingTaskStatus.COMPLETED,
        OnboardingTaskStatus.BLOCKED,
    }:
        raise OnboardingValidationError(
            "Employees can only start, complete, or request help on their own tasks."
        )

    async with transactional(session):
        task, instance = await _load_active_task(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
        )
        if task.responsible_party is not OnboardingTaskResponsibility.EMPLOYEE:
            raise OnboardingTaskNotFoundError("Onboarding task was not found.")

        employee, _ = await _get_employee_for_subject(
            session,
            context=context,
        )
        if employee.application_id != instance.application_id:
            raise OnboardingTaskNotFoundError("Onboarding task was not found.")
        if (
            task.status is OnboardingTaskStatus.BLOCKED
            and command.target_status is OnboardingTaskStatus.IN_PROGRESS
        ):
            raise OnboardingValidationError(
                "Only People Operations can reopen a blocked onboarding task."
            )

        await _apply_onboarding_task_status_update(
            session,
            context=context,
            task=task,
            command=command,
        )

    return task


async def _load_instance_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_instance_id: UUID,
) -> OnboardingInstance:
    """Load and lock one tenant-owned onboarding instance."""
    instance = await session.scalar(
        select(OnboardingInstance)
        .where(
            OnboardingInstance.id == onboarding_instance_id,
            OnboardingInstance.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if instance is None:
        raise OnboardingInstanceNotFoundError(
            "Onboarding instance was not found."
        )

    return instance


async def complete_onboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_instance_id: UUID,
    expected_instance_version: int,
) -> OnboardingInstance:
    """Complete onboarding only when every generated task is completed."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    async with transactional(session):
        instance = await _load_instance_for_update(
            session,
            context=context,
            onboarding_instance_id=onboarding_instance_id,
        )
        _validate_version(
            actual_version=instance.version,
            expected_version=expected_instance_version,
            entity_name="onboarding instance",
        )

        if instance.status is not OnboardingInstanceStatus.ACTIVE:
            raise OnboardingValidationError(
                "Only active onboarding can be completed."
            )

        incomplete_task_id = await session.scalar(
            select(OnboardingTask.id)
            .where(
                OnboardingTask.tenant_id == context.tenant_id,
                OnboardingTask.onboarding_instance_id == instance.id,
                OnboardingTask.status != OnboardingTaskStatus.COMPLETED,
            )
            .limit(1)
        )
        if incomplete_task_id is not None:
            raise OnboardingValidationError(
                "All onboarding tasks must be completed first."
            )

        previous_status = instance.status
        validate_instance_transition(
            previous_status,
            OnboardingInstanceStatus.COMPLETED,
        )
        instance.status = OnboardingInstanceStatus.COMPLETED
        instance.completed_at = datetime.now(UTC)

        _append_instance_history(
            session,
            context=context,
            instance=instance,
            event_type=OnboardingInstanceEventType.COMPLETED,
            from_status=previous_status,
            to_status=instance.status,
        )
        record_audit_event(
            session,
            context=context,
            action="onboarding.completed",
            entity_type="onboarding_instance",
            entity_id=str(instance.id),
        )

        await session.flush()
        await session.refresh(instance)

    return instance


async def cancel_onboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_instance_id: UUID,
    expected_instance_version: int,
) -> OnboardingInstance:
    """Cancel onboarding and atomically cancel all non-terminal tasks."""
    _require_role(context, _ONBOARDING_WRITE_ROLES)

    async with transactional(session):
        instance = await _load_instance_for_update(
            session,
            context=context,
            onboarding_instance_id=onboarding_instance_id,
        )
        _validate_version(
            actual_version=instance.version,
            expected_version=expected_instance_version,
            entity_name="onboarding instance",
        )

        if instance.status is not OnboardingInstanceStatus.ACTIVE:
            raise OnboardingValidationError(
                "Only active onboarding can be cancelled."
            )

        active_tasks = list(
            await session.scalars(
                select(OnboardingTask)
                .where(
                    OnboardingTask.tenant_id == context.tenant_id,
                    OnboardingTask.onboarding_instance_id == instance.id,
                    OnboardingTask.status.not_in(
                        (
                            OnboardingTaskStatus.COMPLETED,
                            OnboardingTaskStatus.CANCELLED,
                        )
                    ),
                )
                .with_for_update()
            )
        )

        for task in active_tasks:
            previous_task_status = task.status
            validate_task_transition(
                previous_task_status,
                OnboardingTaskStatus.CANCELLED,
            )
            task.status = OnboardingTaskStatus.CANCELLED
            task.completed_at = None
            task.blocked_reason = None

            _append_task_history(
                session,
                context=context,
                task=task,
                event_type=OnboardingTaskEventType.CANCELLED,
                from_status=previous_task_status,
                to_status=task.status,
            )

        previous_status = instance.status
        validate_instance_transition(
            previous_status,
            OnboardingInstanceStatus.CANCELLED,
        )
        instance.status = OnboardingInstanceStatus.CANCELLED
        instance.cancelled_at = datetime.now(UTC)

        _append_instance_history(
            session,
            context=context,
            instance=instance,
            event_type=OnboardingInstanceEventType.CANCELLED,
            from_status=previous_status,
            to_status=instance.status,
        )
        record_audit_event(
            session,
            context=context,
            action="onboarding.cancelled",
            entity_type="onboarding_instance",
            entity_id=str(instance.id),
            details={"cancelled_task_count": len(active_tasks)},
        )

        await session.flush()
        await session.refresh(instance)

    return instance
