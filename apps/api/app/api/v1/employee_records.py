"""Private endpoints for employee records managed by MindHire."""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.employee_records import (
    CancelEmployeeOffboardingRequest,
    CreateEmployeeRecordRequest,
    EmployeeDirectoryFilterOptionsResponse,
    EmployeeDirectoryItemResponse,
    EmployeeDirectoryResponse,
    EmployeeOffboardingChecklistResponse,
    EmployeeOffboardingOverviewItemResponse,
    EmployeeOffboardingOverviewResponse,
    EmployeeOffboardingTaskResponse,
    EmployeeOffboardingTaskUpdateRequest,
    EmployeeRecordResponse,
    LinkEmployeeAccountRequest,
    LinkEmployeeAccountResponse,
    MyEmployeeOffboardingTaskResponse,
    MyEmployeeOffboardingTasksResponse,
    OffboardingTemplateResponse,
    OffboardingTemplateTaskResponse,
    ReplaceOffboardingTemplateRequest,
    StartEmployeeOffboardingRequest,
    UpdateEmployeeRecordRequest,
)
from app.core.authorization import Role, TenantContext
from app.db.models.employee import Employee
from app.domains.employees.enums import EmployeeOffboardingTaskStatus, EmployeeStatus
from app.services.employee_offboarding import (
    OffboardingTemplateTaskCommand,
    list_employee_offboarding_overview,
    list_employee_offboarding_tasks,
    list_my_employee_offboarding_tasks,
    list_offboarding_template_tasks,
    replace_offboarding_template_tasks,
    update_employee_offboarding_task,
)
from app.services.employee_records import (
    cancel_employee_offboarding,
    create_application_employee_record,
    get_application_employee_record,
    get_employee_directory_filter_options,
    link_employee_account,
    list_employee_records,
    start_employee_offboarding,
    update_employee_record,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(tags=["Employee records"])
CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
_OFFBOARDING_DETAIL_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})


def _employee_record_response(
    employee: Employee,
    *,
    context: TenantContext,
) -> EmployeeRecordResponse:
    """Serialize an employee and keep planned departure details HR-only."""
    response = EmployeeRecordResponse.model_validate(employee)
    if context.roles.isdisjoint(_OFFBOARDING_DETAIL_ROLES):
        response = response.model_copy(
            update={"last_working_day": None, "offboarding_reason": None}
        )
    return response


@router.get(
    "/employee-records",
    response_model=EmployeeDirectoryResponse,
    summary="List employee records in the workspace",
)
async def list_employee_records_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[EmployeeStatus | None, Query(alias="status")] = None,
    department: Annotated[str | None, Query(max_length=200)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
) -> EmployeeDirectoryResponse:
    """Search and filter employee records within the caller's workspace."""
    rows, total = await list_employee_records(
        session,
        context=context,
        page=page,
        limit=limit,
        query=query,
        status=status_filter,
        department=department,
        location=location,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeeDirectoryResponse(
        items=[
            EmployeeDirectoryItemResponse(
                **_employee_record_response(employee, context=context).model_dump(),
                employee_name=employee_name,
            )
            for employee, employee_name in rows
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/employee-offboarding",
    response_model=EmployeeOffboardingOverviewResponse,
    summary="List active employee offboarding cases",
)
async def employee_offboarding_overview_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=100)] = None,
    task_status: Annotated[EmployeeOffboardingTaskStatus | None, Query()] = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue_only: bool = False,
) -> EmployeeOffboardingOverviewResponse:
    """List current offboarding cases and aggregate their task progress."""
    rows, total = await list_employee_offboarding_overview(
        session,
        context=context,
        page=page,
        limit=limit,
        query=query,
        task_status=task_status,
        due_from=due_from,
        due_to=due_to,
        overdue_only=overdue_only,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeeOffboardingOverviewResponse(
        items=[
            EmployeeOffboardingOverviewItemResponse(
                employee_id=row.employee.id,
                application_id=row.employee.application_id,
                employee_name=row.employee_name,
                job_title=row.employee.job_title,
                department=row.employee.department,
                location=row.employee.location,
                last_working_day=row.employee.last_working_day,
                reason=row.employee.offboarding_reason,
                completed_task_count=row.completed_task_count,
                total_task_count=row.total_task_count,
                overdue_task_count=row.overdue_task_count,
                next_due_date=row.next_due_date,
            )
            for row in rows
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/employee-offboarding/my-tasks",
    response_model=MyEmployeeOffboardingTasksResponse,
    summary="List offboarding tasks assigned to the current member",
)
async def my_employee_offboarding_tasks_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=100)] = None,
    task_status: Annotated[EmployeeOffboardingTaskStatus | None, Query()] = None,
    overdue_only: bool = False,
) -> MyEmployeeOffboardingTasksResponse:
    """List assigned checklist tasks without exposing other offboarding cases."""
    rows, total = await list_my_employee_offboarding_tasks(
        session,
        context=context,
        page=page,
        limit=limit,
        query=query,
        task_status=task_status,
        overdue_only=overdue_only,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return MyEmployeeOffboardingTasksResponse(
        items=[
            MyEmployeeOffboardingTaskResponse(
                id=row.task.id,
                employee_id=row.task.employee_id,
                employee_name=row.employee_name,
                job_title=row.job_title,
                title=row.task.title,
                description=row.task.description,
                due_date=row.task.due_date,
                status=row.task.status,
                completion_notes=row.task.completion_notes,
                completed_at=row.task.completed_at,
                version=row.task.version,
            )
            for row in rows
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/employee-records/filter-options",
    response_model=EmployeeDirectoryFilterOptionsResponse,
    summary="List employee directory filter options",
)
async def employee_directory_filter_options_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> EmployeeDirectoryFilterOptionsResponse:
    """Return values available for department and location filters."""
    departments, locations = await get_employee_directory_filter_options(
        session,
        context=context,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeeDirectoryFilterOptionsResponse(
        departments=departments,
        locations=locations,
    )


def _private_response(result: IdempotencyResult) -> JSONResponse:
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get(
    "/applications/{application_id}/employee-record",
    response_model=EmployeeRecordResponse | None,
    summary="Get the internal employee record for an application",
)
async def get_application_employee_record_endpoint(
    application_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> EmployeeRecordResponse | None:
    employee = await get_application_employee_record(
        session,
        context=context,
        application_id=application_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return _employee_record_response(employee, context=context) if employee else None


@router.post(
    "/applications/{application_id}/employee-record",
    response_model=EmployeeRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an internal employee record from a hired application",
)
async def create_application_employee_record_endpoint(
    application_id: UUID,
    payload: CreateEmployeeRecordRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    async def operation() -> tuple[int, dict[str, Any]]:
        employee = await create_application_employee_record(
            session,
            context=context,
            application_id=application_id,
            employee_number=payload.employee_number,
            work_email=str(payload.work_email) if payload.work_email else None,
            start_date=payload.start_date,
            manager_user_id=payload.manager_user_id,
        )
        return (
            status.HTTP_201_CREATED,
            _employee_record_response(employee, context=context).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_record.create:{application_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.patch(
    "/employee-records/{employee_id}",
    response_model=EmployeeRecordResponse,
    summary="Update an internal employee record",
)
async def update_employee_record_endpoint(
    employee_id: UUID,
    payload: UpdateEmployeeRecordRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    async def operation() -> tuple[int, dict[str, Any]]:
        changes = payload.model_dump(
            exclude={"expected_version"},
            exclude_unset=True,
        )
        employee = await update_employee_record(
            session,
            context=context,
            employee_id=employee_id,
            expected_version=payload.expected_version,
            changes=changes,
        )
        return (
            status.HTTP_200_OK,
            _employee_record_response(employee, context=context).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_record.update:{employee_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/employee-records/{employee_id}/offboarding",
    response_model=EmployeeRecordResponse,
    summary="Start employee offboarding",
)
async def start_employee_offboarding_endpoint(
    employee_id: UUID,
    payload: StartEmployeeOffboardingRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record the planned final working day and reason for an employee."""

    async def operation() -> tuple[int, dict[str, Any]]:
        employee = await start_employee_offboarding(
            session,
            context=context,
            employee_id=employee_id,
            expected_version=payload.expected_version,
            last_working_day=payload.last_working_day,
            reason=payload.reason,
        )
        return (
            status.HTTP_200_OK,
            _employee_record_response(employee, context=context).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_record.offboarding.start:{employee_id}",
        payload={"employee_id": str(employee_id), **payload.model_dump(mode="json")},
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/employee-records/{employee_id}/offboarding/cancel",
    response_model=EmployeeRecordResponse,
    summary="Cancel employee offboarding",
)
async def cancel_employee_offboarding_endpoint(
    employee_id: UUID,
    payload: CancelEmployeeOffboardingRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Restore an employee to active and retain the cancelled plan in audit history."""

    async def operation() -> tuple[int, dict[str, Any]]:
        employee = await cancel_employee_offboarding(
            session,
            context=context,
            employee_id=employee_id,
            expected_version=payload.expected_version,
        )
        return (
            status.HTTP_200_OK,
            _employee_record_response(employee, context=context).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_record.offboarding.cancel:{employee_id}",
        payload={"employee_id": str(employee_id), **payload.model_dump(mode="json")},
        operation=operation,
    )
    return _private_response(result)


@router.get(
    "/employee-offboarding-template",
    response_model=OffboardingTemplateResponse,
    summary="Get the workspace offboarding checklist template",
)
async def get_offboarding_template_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> OffboardingTemplateResponse:
    tasks = await list_offboarding_template_tasks(session, context=context)
    response.headers["Cache-Control"] = "private, no-store"
    return OffboardingTemplateResponse(
        items=[OffboardingTemplateTaskResponse.model_validate(task) for task in tasks]
    )


@router.put(
    "/employee-offboarding-template",
    response_model=OffboardingTemplateResponse,
    summary="Replace the workspace offboarding checklist template",
)
async def replace_offboarding_template_endpoint(
    payload: ReplaceOffboardingTemplateRequest,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> OffboardingTemplateResponse:
    tasks = await replace_offboarding_template_tasks(
        session,
        context=context,
        tasks=tuple(
            OffboardingTemplateTaskCommand(
                title=item.title,
                description=item.description,
                due_days_before_last_working_day=(item.due_days_before_last_working_day),
            )
            for item in payload.items
        ),
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OffboardingTemplateResponse(
        items=[OffboardingTemplateTaskResponse.model_validate(task) for task in tasks]
    )


@router.get(
    "/employee-records/{employee_id}/offboarding-tasks",
    response_model=EmployeeOffboardingChecklistResponse,
    summary="Get the current employee offboarding checklist",
)
async def list_employee_offboarding_tasks_endpoint(
    employee_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> EmployeeOffboardingChecklistResponse:
    rows, completed_count, total_count = await list_employee_offboarding_tasks(
        session,
        context=context,
        employee_id=employee_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeeOffboardingChecklistResponse(
        items=[
            EmployeeOffboardingTaskResponse.model_validate(task).model_copy(
                update={"assigned_to_name": assignee_name}
            )
            for task, assignee_name in rows
        ],
        completed_count=completed_count,
        total_count=total_count,
    )


@router.patch(
    "/employee-offboarding-tasks/{task_id}",
    response_model=EmployeeOffboardingTaskResponse,
    summary="Update an employee offboarding checklist task",
)
async def update_employee_offboarding_task_endpoint(
    task_id: UUID,
    payload: EmployeeOffboardingTaskUpdateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    async def operation() -> tuple[int, dict[str, Any]]:
        changes = payload.model_dump(
            exclude={"expected_version"},
            exclude_unset=True,
        )
        task = await update_employee_offboarding_task(
            session,
            context=context,
            task_id=task_id,
            expected_version=payload.expected_version,
            changes=changes,
        )
        return (
            status.HTTP_200_OK,
            EmployeeOffboardingTaskResponse.model_validate(task).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_offboarding.task.update:{task_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.put(
    "/employee-records/{employee_id}/account",
    response_model=LinkEmployeeAccountResponse,
    summary="Link an employee record to an existing workspace account",
)
async def link_employee_account_endpoint(
    employee_id: UUID,
    payload: LinkEmployeeAccountRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Link or unlink one employee account as an admin or People Ops member."""

    async def operation() -> tuple[int, dict[str, Any]]:
        employee = await link_employee_account(
            session,
            context=context,
            employee_id=employee_id,
            user_id=payload.user_id,
            expected_version=payload.expected_version,
        )
        return (
            status.HTTP_200_OK,
            LinkEmployeeAccountResponse(
                employee_id=employee.id,
                user_id=employee.user_id,
                version=employee.version,
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"employee_record.account_link:{employee_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
