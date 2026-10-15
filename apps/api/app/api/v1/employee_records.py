"""Private endpoints for employee records managed by MindHire."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.employee_records import (
    CreateEmployeeRecordRequest,
    EmployeeDirectoryFilterOptionsResponse,
    EmployeeDirectoryItemResponse,
    EmployeeDirectoryResponse,
    EmployeeRecordResponse,
    UpdateEmployeeRecordRequest,
)
from app.core.authorization import TenantContext
from app.domains.employees.enums import EmployeeStatus
from app.services.employee_records import (
    create_application_employee_record,
    get_application_employee_record,
    get_employee_directory_filter_options,
    list_employee_records,
    update_employee_record,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(tags=["Employee records"])
CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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
                **EmployeeRecordResponse.model_validate(employee).model_dump(),
                employee_name=employee_name,
            )
            for employee, employee_name in rows
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
    return EmployeeRecordResponse.model_validate(employee) if employee else None


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
            EmployeeRecordResponse.model_validate(employee).model_dump(mode="json"),
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
            EmployeeRecordResponse.model_validate(employee).model_dump(mode="json"),
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
