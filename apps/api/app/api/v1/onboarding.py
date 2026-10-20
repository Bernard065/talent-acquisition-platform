"""Version 1 private onboarding workflow HTTP endpoints."""

from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db_session,
    get_object_storage,
    get_tenant_context,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.employee_records import EmployeePortalProfileResponse
from app.api.v1.schemas.onboarding import (
    ApplicationOnboardingResponse,
    AssignOnboardingTaskRequest,
    CreateOnboardingTemplateRequest,
    EmployeePortalOnboardingResponse,
    EmployeePortalTaskResponse,
    ExpectedInstanceVersionRequest,
    OnboardingDocumentReviewQueueItemResponse,
    OnboardingDocumentReviewQueueResponse,
    OnboardingInstanceResponse,
    OnboardingOverviewItemResponse,
    OnboardingOverviewResponse,
    OnboardingTaskActivityItemResponse,
    OnboardingTaskActivityResponse,
    OnboardingTaskDocumentConfirmUploadRequest,
    OnboardingTaskDocumentCreateRequest,
    OnboardingTaskDocumentDownloadAuthorizationResponse,
    OnboardingTaskDocumentResponse,
    OnboardingTaskDocumentReviewRequest,
    OnboardingTaskDocumentUploadAuthorizationRequest,
    OnboardingTaskDocumentUploadAuthorizationResponse,
    OnboardingTaskPrerequisiteResponse,
    OnboardingTaskResponse,
    OnboardingTaskWorklistAssigneeResponse,
    OnboardingTaskWorklistItemResponse,
    OnboardingTaskWorklistResponse,
    OnboardingTemplateListItemResponse,
    OnboardingTemplateListResponse,
    OnboardingTemplateResponse,
    OnboardingTemplateTaskResponse,
    StartOnboardingRequest,
    UpdateEmployeePortalTaskStatusRequest,
    UpdateOnboardingTaskDueDateRequest,
    UpdateOnboardingTaskStatusRequest,
)
from app.core.authorization import TenantContext
from app.core.config import Settings
from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskResponsibility,
    OnboardingTaskStatus,
    OnboardingTaskWorklistView,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.object_storage import ObjectStorage
from app.services.onboarding import (
    CreateOnboardingTemplateCommand,
    OnboardingTemplateTaskDefinition,
    UpdateOnboardingTaskStatusCommand,
    assign_onboarding_task,
    cancel_onboarding,
    complete_onboarding,
    create_onboarding_template,
    get_application_onboarding,
    get_employee_portal_onboarding,
    list_active_onboarding_templates,
    list_onboarding_overview,
    list_onboarding_task_activity,
    list_onboarding_task_prerequisite_states,
    list_onboarding_task_worklist,
    list_onboarding_template_prerequisite_positions,
    start_onboarding,
    update_employee_portal_task_status,
    update_onboarding_task_due_date,
    update_onboarding_task_status,
)
from app.services.onboarding_documents import (
    CreateOnboardingTaskDocumentCommand,
    ReviewOnboardingTaskDocumentCommand,
    confirm_employee_task_document_upload,
    create_employee_task_document_upload_authorization,
    create_employee_task_document_upload_intent,
    create_onboarding_task_document_access_authorization,
    list_documents_for_authorized_tasks,
    list_onboarding_document_review_queue,
    list_onboarding_task_documents,
    review_onboarding_task_document,
)

router = APIRouter(tags=["Onboarding"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
DocumentStorage = Annotated[ObjectStorage, Depends(get_object_storage)]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Prevent onboarding responses from being stored by shared caches."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get(
    "/onboarding-tasks",
    response_model=OnboardingTaskWorklistResponse,
    summary="List onboarding tasks for workspace follow-up",
)
async def list_onboarding_task_worklist_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    view: OnboardingTaskWorklistView = OnboardingTaskWorklistView.OPEN,
    query: Annotated[str | None, Query(max_length=200)] = None,
    assignee_user_id: UUID | None = None,
    unassigned_only: bool = False,
) -> OnboardingTaskWorklistResponse:
    """Search and paginate task-level onboarding work for the tenant."""
    items, assignees, total = await list_onboarding_task_worklist(
        session,
        context=context,
        page=page,
        limit=limit,
        view=view,
        query=query,
        assignee_user_id=assignee_user_id,
        unassigned_only=unassigned_only,
    )
    documents_by_task = await list_documents_for_authorized_tasks(
        session,
        tenant_id=context.tenant_id,
        task_ids=tuple(item.task.id for item in items),
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTaskWorklistResponse(
        items=[
            OnboardingTaskWorklistItemResponse(
                task=OnboardingTaskResponse.model_validate(item.task).model_copy(
                    update={
                        "prerequisites": [
                            OnboardingTaskPrerequisiteResponse(
                                id=prerequisite.id,
                                title=prerequisite.title,
                                status=prerequisite.status,
                            )
                            for prerequisite in item.prerequisites
                        ],
                        "documents": [
                            OnboardingTaskDocumentResponse.model_validate(document)
                            for document in documents_by_task.get(
                                item.task.id,
                                (),
                            )
                        ]
                    }
                ),
                application_id=item.application_id,
                instance_status=item.instance_status,
                employee_name=item.employee_name,
                job_title=item.job_title,
                assignee_display_name=item.assignee_display_name,
                step_number=item.step_number,
                can_update=item.can_update,
                can_progress=item.can_progress,
            )
            for item in items
        ],
        assignees=[
            OnboardingTaskWorklistAssigneeResponse(
                id=assignee_id,
                display_name=display_name,
            )
            for assignee_id, display_name in assignees
        ],
        total=total,
        page=page,
        limit=limit,
        view=view,
    )


@router.get(
    "/onboarding-document-review-queue",
    response_model=OnboardingDocumentReviewQueueResponse,
    summary="List onboarding documents awaiting review",
)
async def list_onboarding_document_review_queue_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=200)] = None,
    document_id: Annotated[UUID | None, Query()] = None,
) -> OnboardingDocumentReviewQueueResponse:
    """Return clean, pending documents for authorized workspace reviewers."""
    items, total = await list_onboarding_document_review_queue(
        session,
        context=context,
        page=page,
        limit=limit,
        query=query,
        document_id=document_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingDocumentReviewQueueResponse(
        items=[
            OnboardingDocumentReviewQueueItemResponse(
                document=OnboardingTaskDocumentResponse.model_validate(item.document),
                onboarding_task_id=item.onboarding_task_id,
                onboarding_instance_id=item.onboarding_instance_id,
                application_id=item.application_id,
                task_title=item.task_title,
                employee_name=item.employee_name,
                job_title=item.job_title,
                previous_versions=[
                    OnboardingTaskDocumentResponse.model_validate(document)
                    for document in item.previous_versions
                ],
            )
            for item in items
        ],
        total=total,
        page=page,
        limit=limit,
    )


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
    template_task_ids = tuple(task.id for _, tasks in templates for task in tasks)
    prerequisite_positions = await list_onboarding_template_prerequisite_positions(
        session,
        task_ids=template_task_ids,
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
                    OnboardingTemplateTaskResponse.model_validate(task).model_copy(
                        update={
                            "prerequisite_task_positions": list(
                                prerequisite_positions.get(task.id, ())
                            )
                        }
                    )
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
    documents_by_task = await list_documents_for_authorized_tasks(
        session,
        tenant_id=context.tenant_id,
        task_ids=tuple(task.id for task in tasks),
    )
    prerequisites_by_task = await list_onboarding_task_prerequisite_states(
        session,
        tenant_id=context.tenant_id,
        tasks=tasks,
    )
    return ApplicationOnboardingResponse(
        instance=OnboardingInstanceResponse.model_validate(instance),
        tasks=[
            OnboardingTaskResponse.model_validate(task).model_copy(
                update={
                    "prerequisites": [
                        OnboardingTaskPrerequisiteResponse(
                            id=prerequisite.id,
                            title=prerequisite.title,
                            status=prerequisite.status,
                        )
                        for prerequisite in prerequisites_by_task.get(task.id, ())
                    ],
                    "documents": [
                        OnboardingTaskDocumentResponse.model_validate(document)
                        for document in documents_by_task.get(task.id, ())
                    ]
                }
            )
            for task in tasks
        ],
    )


@router.get(
    "/onboarding-tasks/{onboarding_task_id}/activity",
    response_model=OnboardingTaskActivityResponse,
    summary="Get activity for an onboarding task",
)
async def get_onboarding_task_activity_endpoint(
    onboarding_task_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> OnboardingTaskActivityResponse:
    """Return task activity to its employee owner or authorized workspace staff."""
    items = await list_onboarding_task_activity(
        session,
        context=context,
        onboarding_task_id=onboarding_task_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTaskActivityResponse(
        items=[
            OnboardingTaskActivityItemResponse(
                id=item.id,
                event_type=item.event_type,
                from_status=item.from_status,
                to_status=item.to_status,
                note=item.note,
                actor_display_name=item.actor_display_name,
                occurred_at=item.occurred_at,
            )
            for item in items
        ]
    )


@router.get(
    "/onboarding-tasks/{onboarding_task_id}/documents",
    response_model=list[OnboardingTaskDocumentResponse],
    summary="List documents submitted for an onboarding task",
)
async def list_onboarding_task_documents_endpoint(
    onboarding_task_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> list[OnboardingTaskDocumentResponse]:
    """Return safe metadata to workspace staff or the employee owner."""
    documents = await list_onboarding_task_documents(
        session,
        context=context,
        onboarding_task_id=onboarding_task_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return [OnboardingTaskDocumentResponse.model_validate(document) for document in documents]


@router.post(
    "/employee-portal/me/onboarding/tasks/{onboarding_task_id}/documents",
    response_model=OnboardingTaskDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an upload intent for an employee onboarding document",
)
async def create_employee_onboarding_task_document_endpoint(
    onboarding_task_id: UUID,
    payload: OnboardingTaskDocumentCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create a pending upload for the authenticated employee's own step."""

    async def operation() -> tuple[int, dict[str, Any]]:
        document = await create_employee_task_document_upload_intent(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            command=CreateOnboardingTaskDocumentCommand(
                original_filename=payload.original_filename,
                declared_content_type=payload.declared_content_type,
                expected_byte_size=payload.expected_byte_size,
                checksum_sha256=payload.checksum_sha256,
                replaces_document_id=payload.replaces_document_id,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            OnboardingTaskDocumentResponse.model_validate(document).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding_task_document.create:{onboarding_task_id}",
        payload={
            "onboarding_task_id": str(onboarding_task_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/onboarding-task-documents/{document_id}/upload-authorizations",
    response_model=OnboardingTaskDocumentUploadAuthorizationResponse,
    summary="Create a short-lived onboarding document upload authorization",
)
async def create_onboarding_document_upload_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    response: Response,
    _: Annotated[OnboardingTaskDocumentUploadAuthorizationRequest, Body(...)],
) -> OnboardingTaskDocumentUploadAuthorizationResponse:
    """Authorize a direct upload using server-owned document metadata."""
    settings: Settings = request.app.state.settings
    upload = await create_employee_task_document_upload_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=timedelta(
            seconds=settings.s3_presigned_upload_expiry_seconds
        ),
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTaskDocumentUploadAuthorizationResponse(
        upload_url=upload.url,
        required_headers=dict(upload.required_headers),
        expires_at=upload.expires_at,
    )


@router.post(
    "/onboarding-task-documents/{document_id}/confirm-upload",
    response_model=OnboardingTaskDocumentResponse,
    summary="Verify and scan an uploaded onboarding document",
)
async def confirm_onboarding_document_upload_endpoint(
    document_id: UUID,
    payload: OnboardingTaskDocumentConfirmUploadRequest,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Verify object metadata and queue malware scanning idempotently."""

    async def operation() -> tuple[int, dict[str, Any]]:
        document = await confirm_employee_task_document_upload(
            session,
            context=context,
            document_id=document_id,
            storage=storage,
        )
        return (
            status.HTTP_200_OK,
            OnboardingTaskDocumentResponse.model_validate(document).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding_task_document.confirm_upload:{document_id}",
        payload={
            "document_id": str(document_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_response(result)


@router.get(
    "/onboarding-task-documents/{document_id}/download-authorizations",
    response_model=OnboardingTaskDocumentDownloadAuthorizationResponse,
    summary="Authorize download of a clean onboarding document",
)
async def create_onboarding_document_download_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    response: Response,
) -> OnboardingTaskDocumentDownloadAuthorizationResponse:
    """Give authorized staff or the employee a short-lived download URL."""
    download = await create_onboarding_task_document_access_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=timedelta(minutes=5),
        preview=False,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTaskDocumentDownloadAuthorizationResponse(
        url=download.url,
        expires_at=download.expires_at,
    )


@router.get(
    "/onboarding-task-documents/{document_id}/preview-authorizations",
    response_model=OnboardingTaskDocumentDownloadAuthorizationResponse,
    summary="Authorize inline preview of a clean onboarding PDF",
)
async def create_onboarding_document_preview_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    response: Response,
) -> OnboardingTaskDocumentDownloadAuthorizationResponse:
    """Give authorized staff or the employee a short-lived preview URL."""
    preview = await create_onboarding_task_document_access_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=timedelta(minutes=5),
        preview=True,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return OnboardingTaskDocumentDownloadAuthorizationResponse(
        url=preview.url,
        expires_at=preview.expires_at,
    )


@router.post(
    "/onboarding-task-documents/{document_id}/reviews",
    response_model=OnboardingTaskDocumentResponse,
    summary="Accept an onboarding document or request a replacement",
)
async def review_onboarding_task_document_endpoint(
    document_id: UUID,
    payload: OnboardingTaskDocumentReviewRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Record an authorized reviewer decision idempotently."""

    async def operation() -> tuple[int, dict[str, Any]]:
        document = await review_onboarding_task_document(
            session,
            context=context,
            document_id=document_id,
            command=ReviewOnboardingTaskDocumentCommand(
                expected_document_version=payload.expected_document_version,
                decision=payload.decision,
                comment=payload.comment,
            ),
        )
        return (
            status.HTTP_200_OK,
            OnboardingTaskDocumentResponse.model_validate(document).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"onboarding_task_document.review:{document_id}",
        payload={
            "document_id": str(document_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )
    return _private_response(result)


@router.get(
    "/employee-portal/me/onboarding",
    response_model=EmployeePortalOnboardingResponse,
    summary="Get the authenticated employee's own onboarding checklist",
)
async def get_employee_portal_onboarding_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> EmployeePortalOnboardingResponse:
    """Resolve the linked employee from the verified subject, never a client ID."""
    employee, full_name, instance, tasks = await get_employee_portal_onboarding(
        session,
        context=context,
    )
    documents_by_task = await list_documents_for_authorized_tasks(
        session,
        tenant_id=context.tenant_id,
        task_ids=tuple(task.id for task in tasks),
    )
    prerequisites_by_task = await list_onboarding_task_prerequisite_states(
        session,
        tenant_id=context.tenant_id,
        tasks=tasks,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeePortalOnboardingResponse(
        profile=EmployeePortalProfileResponse(
            full_name=full_name,
            work_email=employee.work_email,
            start_date=employee.start_date,
            job_title=employee.job_title,
            department=employee.department,
            location=employee.location,
            status=employee.status,
        ),
        onboarding_status=instance.status if instance else None,
        started_at=instance.started_at if instance else None,
        completed_at=instance.completed_at if instance else None,
        tasks=[
            EmployeePortalTaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                due_at=task.due_at,
                responsible_party=task.responsible_party,
                requires_document_upload=task.requires_document_upload,
                requires_document_review=task.requires_document_review,
                status=task.status,
                blocked_reason=(
                    task.blocked_reason
                    if task.responsible_party
                    is OnboardingTaskResponsibility.EMPLOYEE
                    else None
                ),
                resolution_note=(
                    task.resolution_note
                    if task.responsible_party
                    is OnboardingTaskResponsibility.EMPLOYEE
                    else None
                ),
                completed_at=task.completed_at,
                version=task.version,
                can_update=(
                    instance is not None
                    and instance.status is OnboardingInstanceStatus.ACTIVE
                    and task.responsible_party is OnboardingTaskResponsibility.EMPLOYEE
                    and task.status
                    in {
                        OnboardingTaskStatus.NOT_STARTED,
                        OnboardingTaskStatus.IN_PROGRESS,
                    }
                    and all(
                        prerequisite.status is OnboardingTaskStatus.COMPLETED
                        for prerequisite in prerequisites_by_task.get(task.id, ())
                    )
                ),
                prerequisites=[
                    OnboardingTaskPrerequisiteResponse(
                        id=prerequisite.id,
                        title=prerequisite.title,
                        status=prerequisite.status,
                    )
                    for prerequisite in prerequisites_by_task.get(task.id, ())
                ],
                documents=[
                    OnboardingTaskDocumentResponse.model_validate(document)
                    for document in documents_by_task.get(task.id, ())
                ],
            )
            for task in tasks
        ],
    )


@router.patch(
    "/employee-portal/me/onboarding/tasks/{onboarding_task_id}/status",
    response_model=EmployeePortalTaskResponse,
    summary="Update the authenticated employee's own onboarding task",
)
async def update_employee_portal_task_status_endpoint(
    onboarding_task_id: UUID,
    payload: UpdateEmployeePortalTaskStatusRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Let an employee progress or request help for a task they own."""

    async def operation() -> tuple[int, dict[str, Any]]:
        task = await update_employee_portal_task_status(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            command=UpdateOnboardingTaskStatusCommand(
                expected_version=payload.expected_version,
                target_status=OnboardingTaskStatus(payload.target_status),
                blocked_reason=payload.blocked_reason,
            ),
        )
        return (
            status.HTTP_200_OK,
            EmployeePortalTaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                due_at=task.due_at,
                responsible_party=task.responsible_party,
                requires_document_upload=task.requires_document_upload,
                requires_document_review=task.requires_document_review,
                status=task.status,
                blocked_reason=task.blocked_reason,
                resolution_note=task.resolution_note,
                completed_at=task.completed_at,
                version=task.version,
                can_update=False,
                documents=[],
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=(
            "employee_portal_onboarding_task.update_status:"
            f"{onboarding_task_id}"
        ),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


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
                        responsible_party=task.responsible_party,
                        requires_document_upload=task.requires_document_upload,
                        requires_document_review=task.requires_document_review,
                        prerequisite_task_positions=tuple(
                            task.prerequisite_task_positions
                        ),
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
    "/onboarding-tasks/{onboarding_task_id}/due-date",
    response_model=OnboardingTaskResponse,
    summary="Update an onboarding task due date",
)
async def update_onboarding_task_due_date_endpoint(
    onboarding_task_id: UUID,
    payload: UpdateOnboardingTaskDueDateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Change or clear a task due date with optimistic concurrency."""

    async def operation() -> tuple[int, dict[str, Any]]:
        task = await update_onboarding_task_due_date(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            due_date=payload.due_date,
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
        operation_name=f"onboarding_task.update_due_date:{onboarding_task_id}",
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
                resolution_note=payload.resolution_note,
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
