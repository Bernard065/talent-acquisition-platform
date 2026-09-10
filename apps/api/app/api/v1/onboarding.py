"""Version 1 private onboarding workflow HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.onboarding import (
    AssignOnboardingTaskRequest,
    CreateOnboardingTemplateRequest,
    ExpectedInstanceVersionRequest,
    OnboardingInstanceResponse,
    OnboardingTaskResponse,
    OnboardingTemplateResponse,
    StartOnboardingRequest,
    UpdateOnboardingTaskStatusRequest,
)
from app.core.authorization import TenantContext
from app.services.idempotency import IdempotencyResult, execute_idempotently
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

router = APIRouter(tags=["Onboarding"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Prevent onboarding responses from being stored by shared caches."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "/onboarding-templates",
    response_model=OnboardingTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an onboarding template",
)
async def create_onboarding_template_endpoint(
    payload: CreateOnboardingTemplateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create an immutable tenant-owned onboarding template version."""

    async def operation() -> tuple[int, dict[str, Any]]:
        template = await create_onboarding_template(
            session,
            context=context,
            command=CreateOnboardingTemplateCommand(
                name=payload.name,
                version=payload.version,
                tasks=tuple(
                    OnboardingTemplateTaskDefinition(
                        title=task.title,
                        description=task.description,
                        due_offset_days=task.due_offset_days,
                        default_assignee_role=task.default_assignee_role,
                    )
                    for task in payload.tasks
                ),
            ),
        )
        return (
            status.HTTP_201_CREATED,
            OnboardingTemplateResponse.model_validate(template).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="onboarding_template.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/applications/{application_id}/onboarding-instances",
    response_model=OnboardingInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start onboarding for a hired application",
)
async def start_onboarding_endpoint(
    application_id: UUID,
    payload: StartOnboardingRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create onboarding and its task snapshots for a hired application."""

    async def operation() -> tuple[int, dict[str, Any]]:
        instance = await start_onboarding(
            session,
            context=context,
            application_id=application_id,
            onboarding_template_id=payload.onboarding_template_id,
        )
        return (
            status.HTTP_201_CREATED,
            OnboardingInstanceResponse.model_validate(instance).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding.start:{application_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/onboarding-tasks/{onboarding_task_id}/assignee",
    response_model=OnboardingTaskResponse,
    summary="Assign an onboarding task",
)
async def assign_onboarding_task_endpoint(
    onboarding_task_id: UUID,
    payload: AssignOnboardingTaskRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Assign a task to a tenant-owned user."""

    async def operation() -> tuple[int, dict[str, Any]]:
        task = await assign_onboarding_task(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            assignee_user_id=payload.assignee_user_id,
            expected_task_version=payload.expected_task_version,
        )
        return (
            status.HTTP_200_OK,
            OnboardingTaskResponse.model_validate(task).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding_task.assign:{onboarding_task_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.patch(
    "/onboarding-tasks/{onboarding_task_id}/status",
    response_model=OnboardingTaskResponse,
    summary="Update an onboarding task status",
)
async def update_onboarding_task_status_endpoint(
    onboarding_task_id: UUID,
    payload: UpdateOnboardingTaskStatusRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Apply one controlled task status transition."""

    async def operation() -> tuple[int, dict[str, Any]]:
        task = await update_onboarding_task_status(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=payload.expected_version,
                target_status=payload.target_status,
                blocked_reason=payload.blocked_reason,
            ),
        )
        return (
            status.HTTP_200_OK,
            OnboardingTaskResponse.model_validate(task).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding_task.update_status:{onboarding_task_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/onboarding-instances/{onboarding_instance_id}/complete",
    response_model=OnboardingInstanceResponse,
    summary="Complete onboarding",
)
async def complete_onboarding_endpoint(
    onboarding_instance_id: UUID,
    payload: ExpectedInstanceVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Complete onboarding only after every task has been completed."""

    async def operation() -> tuple[int, dict[str, Any]]:
        instance = await complete_onboarding(
            session,
            context=context,
            onboarding_instance_id=onboarding_instance_id,
            expected_instance_version=payload.expected_instance_version,
        )
        return (
            status.HTTP_200_OK,
            OnboardingInstanceResponse.model_validate(instance).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding.complete:{onboarding_instance_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/onboarding-instances/{onboarding_instance_id}/cancel",
    response_model=OnboardingInstanceResponse,
    summary="Cancel onboarding",
)
async def cancel_onboarding_endpoint(
    onboarding_instance_id: UUID,
    payload: ExpectedInstanceVersionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Cancel active onboarding and all incomplete onboarding tasks."""

    async def operation() -> tuple[int, dict[str, Any]]:
        instance = await cancel_onboarding(
            session,
            context=context,
            onboarding_instance_id=onboarding_instance_id,
            expected_instance_version=payload.expected_instance_version,
        )
        return (
            status.HTTP_200_OK,
            OnboardingInstanceResponse.model_validate(instance).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding.cancel:{onboarding_instance_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
