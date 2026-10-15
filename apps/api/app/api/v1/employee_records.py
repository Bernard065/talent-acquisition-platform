"""Private endpoints for employee records managed by MindHire."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.employee_records import (
    CreateEmployeeRecordRequest,
    EmployeeRecordResponse,
    UpdateEmployeeRecordRequest,
)
from app.core.authorization import TenantContext
from app.services.employee_records import (
    create_application_employee_record,
    get_application_employee_record,
    update_employee_record,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(tags=["Employee records"])
CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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
