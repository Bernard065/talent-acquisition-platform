"""Tenant-scoped employee records managed directly in MindHire."""

from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.employee import Employee
from app.db.models.identity import User
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.candidates.enums import ApplicationStatus
from app.domains.employees.enums import EmployeeOffboardingReason, EmployeeStatus
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.onboarding_errors import (
    EmployeeRecordNotFoundError,
    OnboardingAccessDeniedError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)

_EMPLOYEE_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS, Role.RECRUITER})
_EMPLOYEE_ACCOUNT_ADMIN_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS}
)
_EMPLOYEE_OFFBOARDING_ADMIN_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS}
)


def _require_employee_access(context: TenantContext) -> None:
    if context.roles.isdisjoint(_EMPLOYEE_ROLES):
        raise OnboardingAccessDeniedError("Caller is not permitted to manage employee records.")


def _require_employee_account_admin(context: TenantContext) -> None:
    if context.roles.isdisjoint(_EMPLOYEE_ACCOUNT_ADMIN_ROLES):
        raise OnboardingAccessDeniedError(
            "Only workspace admins and People Operations can link employee accounts."
        )


def _require_employee_offboarding_admin(context: TenantContext) -> None:
    if context.roles.isdisjoint(_EMPLOYEE_OFFBOARDING_ADMIN_ROLES):
        raise OnboardingAccessDeniedError(
            "Only workspace admins and People Operations can manage employee offboarding."
        )


async def list_employee_records(
    session: AsyncSession,
    *,
    context: TenantContext,
    page: int,
    limit: int,
    query: str | None = None,
    status: EmployeeStatus | None = None,
    department: str | None = None,
    location: str | None = None,
) -> tuple[list[tuple[Employee, str]], int]:
    """Return a tenant-scoped, paginated employee directory page."""
    _require_employee_access(context)
    filters: list[ColumnElement[bool]] = [Employee.tenant_id == context.tenant_id]
    if status is not None:
        filters.append(Employee.status == status)
    if department:
        filters.append(func.lower(Employee.department) == department.strip().casefold())
    if location:
        filters.append(func.lower(Employee.location) == location.strip().casefold())
    if query and query.strip():
        search_term = f"%{query.strip()}%"
        filters.append(
            or_(
                Candidate.full_name.ilike(search_term),
                Employee.employee_number.ilike(search_term),
                Employee.work_email.ilike(search_term),
                Employee.job_title.ilike(search_term),
                Employee.department.ilike(search_term),
                Employee.location.ilike(search_term),
            )
        )

    tenant_candidate_join = and_(
        Candidate.id == Employee.candidate_id,
        Candidate.tenant_id == Employee.tenant_id,
    )
    total = await session.scalar(
        select(func.count(Employee.id))
        .select_from(Employee)
        .join(Candidate, tenant_candidate_join)
        .where(*filters)
    )
    rows = (
        await session.execute(
            select(Employee, Candidate.full_name)
            .join(Candidate, tenant_candidate_join)
            .where(*filters)
            .order_by(
                Employee.start_date.desc().nullslast(),
                Employee.created_at.desc(),
                Employee.id.desc(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return [(employee, employee_name) for employee, employee_name in rows], total or 0


async def get_employee_directory_filter_options(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> tuple[list[str], list[str]]:
    """Return available employee departments and locations for this tenant."""
    _require_employee_access(context)
    departments = list(
        await session.scalars(
            select(Employee.department)
            .where(
                Employee.tenant_id == context.tenant_id,
                Employee.department.is_not(None),
            )
            .distinct()
            .order_by(Employee.department)
        )
    )
    locations = list(
        await session.scalars(
            select(Employee.location)
            .where(
                Employee.tenant_id == context.tenant_id,
                Employee.location.is_not(None),
            )
            .distinct()
            .order_by(Employee.location)
        )
    )
    return [value for value in departments if value], [value for value in locations if value]


async def get_application_employee_record(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> Employee | None:
    """Return an employee record for a hired tenant application, if created."""
    _require_employee_access(context)
    application = await session.scalar(
        select(Application.id).where(
            Application.id == application_id,
            Application.tenant_id == context.tenant_id,
        )
    )
    if application is None:
        raise ApplicationNotFoundError("Application was not found.")

    return cast(
        Employee | None,
        await session.scalar(
            select(Employee).where(
                Employee.tenant_id == context.tenant_id,
                Employee.application_id == application_id,
            )
        ),
    )


async def create_application_employee_record(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    employee_number: str | None,
    work_email: str | None,
    start_date: date | None,
    manager_user_id: UUID | None,
) -> Employee:
    """Create an internal employee record from a hired application."""
    _require_employee_access(context)

    normalized_number = employee_number.strip() if employee_number else None
    normalized_email = work_email.strip().lower() if work_email else None
    if normalized_number == "":
        normalized_number = None
    if normalized_email == "":
        normalized_email = None

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
                "An employee record can only be created for a hired application."
            )

        existing = await session.scalar(
            select(Employee.id).where(
                Employee.tenant_id == context.tenant_id,
                Employee.application_id == application_id,
            )
        )
        if existing is not None:
            raise OnboardingValidationError(
                "An employee record already exists for this application."
            )

        candidate = await session.scalar(
            select(Candidate).where(
                Candidate.id == application.candidate_id,
                Candidate.tenant_id == context.tenant_id,
            )
        )
        requisition = await session.scalar(
            select(Requisition).where(
                Requisition.id == application.requisition_id,
                Requisition.tenant_id == context.tenant_id,
            )
        )
        if candidate is None or requisition is None:
            raise ApplicationNotFoundError("Application was not found.")

        if manager_user_id is not None:
            manager_exists = await session.scalar(
                select(User.id).where(
                    User.id == manager_user_id,
                    User.tenant_id == context.tenant_id,
                )
            )
            if manager_exists is None:
                raise OnboardingValidationError(
                    "The selected manager is not a member of this workspace."
                )

        if normalized_number is not None:
            number_exists = await session.scalar(
                select(Employee.id).where(
                    Employee.tenant_id == context.tenant_id,
                    Employee.employee_number == normalized_number,
                )
            )
            if number_exists is not None:
                raise OnboardingValidationError("That employee number is already in use.")
        if normalized_email is not None:
            email_exists = await session.scalar(
                select(Employee.id).where(
                    Employee.tenant_id == context.tenant_id,
                    func.lower(Employee.work_email) == normalized_email,
                )
            )
            if email_exists is not None:
                raise OnboardingValidationError("That work email is already in use.")

        employee = Employee(
            tenant_id=context.tenant_id,
            application_id=application.id,
            candidate_id=candidate.id,
            employee_number=normalized_number,
            work_email=normalized_email,
            start_date=start_date,
            job_title=requisition.title,
            department=requisition.department,
            location=requisition.location,
            manager_user_id=manager_user_id,
            status=EmployeeStatus.PREBOARDING,
            created_by_subject=context.subject,
        )
        session.add(employee)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="employee_record.created",
            entity_type="employee",
            entity_id=str(employee.id),
            details={"application_id": str(application.id)},
        )
        await session.refresh(employee)

    return employee


async def update_employee_record(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee_id: UUID,
    expected_version: int,
    changes: dict[str, object],
) -> Employee:
    """Update internal employee details with tenant and version checks."""
    _require_employee_access(context)
    allowed_fields = {
        "employee_number",
        "work_email",
        "start_date",
        "job_title",
        "department",
        "location",
        "manager_user_id",
        "status",
    }
    if not changes or changes.keys() - allowed_fields:
        raise OnboardingValidationError("Employee record updates are invalid.")

    async with transactional(session):
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if employee is None:
            raise EmployeeRecordNotFoundError("Employee record was not found.")
        if employee.version != expected_version:
            raise OnboardingVersionConflictError(
                "Employee record has changed; reload before saving."
            )

        normalized_changes: dict[str, object] = {}
        if "employee_number" in changes:
            value = changes["employee_number"]
            normalized_changes["employee_number"] = (
                value.strip() or None if isinstance(value, str) else value
            )
        if "work_email" in changes:
            value = changes["work_email"]
            normalized_changes["work_email"] = (
                value.strip().lower() or None if isinstance(value, str) else value
            )
        if "job_title" in changes:
            value = changes["job_title"]
            if not isinstance(value, str) or not value.strip():
                raise OnboardingValidationError("Job title is required.")
            normalized_changes["job_title"] = value.strip()
        if "department" in changes or "location" in changes:
            for field_name in ("department", "location"):
                if field_name in changes:
                    value = changes[field_name]
                    normalized_changes[field_name] = (
                        value.strip() or None if isinstance(value, str) else value
                    )
        if "manager_user_id" in changes:
            manager_user_id = changes["manager_user_id"]
            if manager_user_id is not None:
                manager_exists = await session.scalar(
                    select(User.id).where(
                        User.id == manager_user_id,
                        User.tenant_id == context.tenant_id,
                    )
                )
                if manager_exists is None:
                    raise OnboardingValidationError(
                        "The selected manager is not a member of this workspace."
                    )
            normalized_changes["manager_user_id"] = manager_user_id
        if "start_date" in changes:
            normalized_changes["start_date"] = changes["start_date"]
        if "status" in changes:
            next_status = changes["status"]
            if not isinstance(next_status, EmployeeStatus):
                raise OnboardingValidationError("Employee status is invalid.")
            effective_start_date = normalized_changes.get(
                "start_date",
                employee.start_date,
            )
            if next_status is EmployeeStatus.ACTIVE and effective_start_date is None:
                raise OnboardingValidationError(
                    "Add a start date before marking this employee active."
                )
            allowed_statuses = {
                EmployeeStatus.PREBOARDING: {
                    EmployeeStatus.ACTIVE,
                    EmployeeStatus.INACTIVE,
                },
                EmployeeStatus.ACTIVE: set(),
                EmployeeStatus.OFFBOARDING: set(),
                EmployeeStatus.INACTIVE: {EmployeeStatus.ACTIVE},
            }
            if (
                next_status != employee.status
                and next_status not in allowed_statuses[employee.status]
            ):
                if next_status is EmployeeStatus.OFFBOARDING:
                    raise OnboardingValidationError(
                        "Use the offboarding action to record a last working day and reason."
                    )
                if (
                    employee.status is EmployeeStatus.ACTIVE
                    and next_status is EmployeeStatus.INACTIVE
                ):
                    raise OnboardingValidationError(
                        "Start the offboarding workflow before marking an active employee inactive."
                    )
                raise OnboardingValidationError("The employee status transition is not allowed.")
            normalized_changes["status"] = next_status

        for field_name in ("employee_number", "work_email"):
            value = normalized_changes.get(field_name)
            if value is None:
                continue
            duplicate_statement = select(Employee.id).where(
                Employee.tenant_id == context.tenant_id,
                getattr(Employee, field_name) == value,
                Employee.id != employee.id,
            )
            if field_name == "work_email":
                duplicate_statement = select(Employee.id).where(
                    Employee.tenant_id == context.tenant_id,
                    func.lower(Employee.work_email) == value,
                    Employee.id != employee.id,
                )
            if await session.scalar(duplicate_statement) is not None:
                raise OnboardingValidationError(
                    f"That {field_name.replace('_', ' ')} is already in use."
                )

        for field_name, value in normalized_changes.items():
            setattr(employee, field_name, value)
        record_audit_event(
            session,
            context=context,
            action="employee_record.updated",
            entity_type="employee",
            entity_id=str(employee.id),
            details={"updated_fields": sorted(normalized_changes)},
        )
        await session.flush()
        await session.refresh(employee)

    return employee


async def start_employee_offboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee_id: UUID,
    expected_version: int,
    last_working_day: date,
    reason: EmployeeOffboardingReason,
) -> Employee:
    """Record an employee's planned departure without deleting their history."""
    _require_employee_offboarding_admin(context)

    async with transactional(session):
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if employee is None:
            raise EmployeeRecordNotFoundError("Employee record was not found.")
        if employee.version != expected_version:
            raise OnboardingVersionConflictError(
                "Employee record has changed; reload before starting offboarding."
            )
        if employee.status is not EmployeeStatus.ACTIVE:
            raise OnboardingValidationError(
                "Only an active employee can start offboarding."
            )
        if employee.start_date is not None and last_working_day < employee.start_date:
            raise OnboardingValidationError(
                "The last working day cannot be before the employee's start date."
            )

        employee.status = EmployeeStatus.OFFBOARDING
        employee.last_working_day = last_working_day
        employee.offboarding_reason = reason
        record_audit_event(
            session,
            context=context,
            action="employee_record.offboarding_started",
            entity_type="employee",
            entity_id=str(employee.id),
            details={
                "last_working_day": last_working_day.isoformat(),
                "reason": reason.value,
            },
        )
        await session.flush()
        await session.refresh(employee)

    return employee


async def cancel_employee_offboarding(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee_id: UUID,
    expected_version: int,
) -> Employee:
    """Cancel a planned departure and preserve its details in audit history."""
    _require_employee_offboarding_admin(context)

    async with transactional(session):
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if employee is None:
            raise EmployeeRecordNotFoundError("Employee record was not found.")
        if employee.version != expected_version:
            raise OnboardingVersionConflictError(
                "Employee record has changed; reload before cancelling offboarding."
            )
        if employee.status is not EmployeeStatus.OFFBOARDING:
            raise OnboardingValidationError(
                "Only an employee in offboarding can cancel a planned departure."
            )

        previous_last_working_day = employee.last_working_day
        previous_reason = employee.offboarding_reason
        employee.status = EmployeeStatus.ACTIVE
        employee.last_working_day = None
        employee.offboarding_reason = None
        record_audit_event(
            session,
            context=context,
            action="employee_record.offboarding_cancelled",
            entity_type="employee",
            entity_id=str(employee.id),
            details={
                "last_working_day": (
                    previous_last_working_day.isoformat()
                    if previous_last_working_day is not None
                    else None
                ),
                "reason": previous_reason.value if previous_reason is not None else None,
            },
        )
        await session.flush()
        await session.refresh(employee)

    return employee


async def link_employee_account(
    session: AsyncSession,
    *,
    context: TenantContext,
    employee_id: UUID,
    user_id: UUID | None,
    expected_version: int,
) -> Employee:
    """Link one tenant employee record to an existing tenant identity."""
    _require_employee_account_admin(context)

    async with transactional(session):
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if employee is None:
            raise EmployeeRecordNotFoundError("Employee record was not found.")
        if employee.version != expected_version:
            raise OnboardingVersionConflictError(
                "Employee record has changed; reload before linking an account."
            )
        if employee.user_id == user_id:
            return employee

        if user_id is not None:
            user = await session.scalar(
                select(User)
                .where(
                    User.id == user_id,
                    User.tenant_id == context.tenant_id,
                )
                .with_for_update()
            )
            if user is None:
                raise OnboardingValidationError(
                    "Select an existing member of this workspace."
                )
            candidate_email = await session.scalar(
                select(Candidate.email).where(
                    Candidate.id == employee.candidate_id,
                    Candidate.tenant_id == context.tenant_id,
                )
            )
            accepted_emails = {
                value.strip().casefold()
                for value in (candidate_email, employee.work_email)
                if value
            }
            if user.email.strip().casefold() not in accepted_emails:
                raise OnboardingValidationError(
                    "The account email must match the employee's candidate or work email."
                )
            linked_employee_id = await session.scalar(
                select(Employee.id).where(
                    Employee.user_id == user_id,
                    Employee.id != employee.id,
                )
            )
            if linked_employee_id is not None:
                raise OnboardingValidationError(
                    "This workspace account is already linked to another employee."
                )

        previous_user_id = employee.user_id
        employee.user_id = user_id
        record_audit_event(
            session,
            context=context,
            action="employee_record.account_linked"
            if user_id is not None
            else "employee_record.account_unlinked",
            entity_type="employee",
            entity_id=str(employee.id),
            details={
                "previous_user_id": str(previous_user_id)
                if previous_user_id
                else None,
                "user_id": str(user_id) if user_id else None,
            },
        )
        await session.flush()
        await session.refresh(employee)

    return employee


