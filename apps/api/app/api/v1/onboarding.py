"""Version 1 private onboarding workflow HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.onboarding import (
    ApplicationOnboardingResponse,
    AssignOnboardingTaskRequest,
    CreateOnboardingTemplateRequest,
    ExpectedInstanceVersionRequest,
    OnboardingInstanceResponse,
    OnboardingOverviewItemResponse,
    OnboardingOverviewResponse,
    OnboardingTaskResponse,
    OnboardingTemplateListItemResponse,
    OnboardingTemplateListResponse,
    OnboardingTemplateResponse,
    OnboardingTemplateTaskResponse,
    StartOnboardingRequest,
    UpdateOnboardingTaskStatusRequest,
)
from app.core.authorization import TenantContext
from app.domains.onboarding.enums import OnboardingInstanceStatus
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    UpdateOnboardingTaskStatusCommand,
    assign_onboarding_task,
    cancel_onboarding,
    complete_onboarding,
    create_onboarding_template,
    get_application_onboarding,
    list_active_onboarding_templates,
    list_onboarding_overview,
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


@router.get(
    "/onboarding-instances",
    response_model=OnboardingOverviewResponse,
    summary="List workspace onboarding plans",
)
async def list_onboarding_overview_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        OnboardingInstanceStatus | None,
        Query(alias="status"),
    ] = None,
    overdue_only: bool = False,
) -> OnboardingOverviewResponse:
    """Search and paginate onboarding plans in the caller's workspace."""
    items, total, active_plan_count, overdue_task_count = (
        await list_onboarding_overview(
            session,
            context=context,
            page=page,
            limit=limit,
            query=query,
            status=status_filter,
            overdue_only=overdue_only,
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingOverviewResponse(
        items=[
            OnboardingOverviewItemResponse(
                instance=OnboardingInstanceResponse.model_validate(instance),
                employee_name=employee_name,
                job_title=job_title,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                overdue_tasks=overdue_tasks,
            )
            for (
                instance,
                employee_name,
                job_title,
                total_tasks,
                completed_tasks,
                overdue_tasks,
            ) in items
        ],
        total=total,
        page=page,
        limit=limit,
        active_plan_count=active_plan_count,
        overdue_task_count=overdue_task_count,
    )


@router.get(
    "/onboarding-templates",
    response_model=OnboardingTemplateListResponse,
    summary="List active onboarding templates",
)
async def list_onboarding_templates_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> OnboardingTemplateListResponse:
    """List tenant templates recruiters can use for hired applications."""
    templates = await list_active_onboarding_templates(
        session,
        context=context,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTemplateListResponse(
        items=[
            OnboardingTemplateListItemResponse(
                id=template.id,
                name=template.name,
                version=template.version,
                is_active=template.is_active,
                created_at=template.created_at,
                tasks=[
                    OnboardingTemplateTaskResponse.model_validate(task)
                    for task in tasks
                ],
            )
            for template, tasks in templates
        ]
    )


@router.get(
    "/applications/{application_id}/onboarding",
    response_model=ApplicationOnboardingResponse,
    summary="Get onboarding for an application",
)
async def get_application_onboarding_endpoint(
    application_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> ApplicationOnboardingResponse:
    """Return onboarding task progress without returning candidate data."""
    result = await get_application_onboarding(
        session,
        context=context,
        application_id=application_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    if result is None:
        return ApplicationOnboardingResponse(instance=None, tasks=[])

    instance, tasks = result
    return ApplicationOnboardingResponse(
        instance=OnboardingInstanceResponse.model_validate(instance),
        tasks=[OnboardingTaskResponse.model_validate(task) for task in tasks],
    )


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
