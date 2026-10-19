"""Secure employee onboarding document upload and access services."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.employee import Employee
from app.db.models.identity import User
from app.db.models.onboarding import (
    OnboardingInstance,
    OnboardingTask,
    OnboardingTaskDocument,
    OnboardingTemplateTask,
)
from app.db.transactions import transactional
from app.domains.documents.enums import MalwareScanVerdict
from app.domains.employees.enums import EmployeeStatus
from app.domains.notifications.enums import NotificationEventType
from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskDocumentReviewDecision,
    OnboardingTaskDocumentReviewStatus,
    OnboardingTaskDocumentStatus,
    OnboardingTaskResponsibility,
    OnboardingTaskStatus,
)
from app.services.audit import record_audit_event
from app.services.malware_scanner import MalwareScanResult
from app.services.notification_publishing import (
    enqueue_notification_request,
    enqueue_notifications_for_roles,
)
from app.services.object_storage import (
    ObjectStorage,
    ObjectStorageError,
    PresignedDownload,
    PresignedUpload,
    StoredObjectMetadata,
    onboarding_task_document_object_key,
)
from app.services.onboarding_errors import (
    EmployeePortalRecordNotFoundError,
    OnboardingAccessDeniedError,
    OnboardingTaskNotFoundError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)
from app.services.outbox import enqueue_outbox_event

_DOCUMENT_ACCESS_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_DOCUMENT_REVIEW_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.PEOPLE_OPERATIONS,
    }
)
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
_MAX_DOCUMENTS_PER_TASK = 10
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class OnboardingDocumentStorageError(RuntimeError):
    """Raised when private object storage cannot complete a document operation."""


@dataclass(frozen=True, slots=True)
class CreateOnboardingTaskDocumentCommand:
    """Validated metadata for a new employee-owned task document."""

    original_filename: str
    declared_content_type: str
    expected_byte_size: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        filename = self.original_filename.strip()
        if (
            not filename
            or len(filename) > 255
            or "/" in filename
            or "\\" in filename
            or any(ord(character) < 32 for character in filename)
        ):
            raise OnboardingValidationError("Document filename is invalid.")
        if self.declared_content_type not in _ALLOWED_CONTENT_TYPES:
            raise OnboardingValidationError("Document file type is not supported.")
        if not 0 < self.expected_byte_size <= _MAX_DOCUMENT_BYTES:
            raise OnboardingValidationError(
                "Document size must be between 1 byte and 10 MiB."
            )
        checksum = self.checksum_sha256.lower()
        if not _SHA256_PATTERN.fullmatch(checksum):
            raise OnboardingValidationError("Document checksum is invalid.")
        object.__setattr__(self, "original_filename", filename)
        object.__setattr__(self, "checksum_sha256", checksum)


@dataclass(frozen=True, slots=True)
class ReviewOnboardingTaskDocumentCommand:
    """Validated reviewer decision for one clean document awaiting review."""

    expected_document_version: int
    decision: OnboardingTaskDocumentReviewDecision
    comment: str | None = None

    def __post_init__(self) -> None:
        normalized_comment = self.comment.strip() if self.comment is not None else None
        if self.expected_document_version < 1:
            raise OnboardingValidationError(
                "Document version must be a positive integer."
            )
        if (
            self.decision is OnboardingTaskDocumentReviewDecision.CHANGES_REQUESTED
            and not normalized_comment
        ):
            raise OnboardingValidationError(
                "Add a reason so the employee knows what to change."
            )
        if normalized_comment is not None and len(normalized_comment) > 2000:
            raise OnboardingValidationError(
                "Review comments cannot exceed 2000 characters."
            )
        object.__setattr__(self, "comment", normalized_comment or None)


@dataclass(frozen=True, slots=True)
class OnboardingDocumentReviewQueueItem:
    """A pending document with minimal employee and task context for reviewers."""

    document: OnboardingTaskDocument
    onboarding_task_id: UUID
    onboarding_instance_id: UUID
    application_id: UUID
    task_title: str
    employee_name: str
    job_title: str


async def list_onboarding_document_review_queue(
    session: AsyncSession,
    *,
    context: TenantContext,
    page: int,
    limit: int,
    query: str | None = None,
) -> tuple[list[OnboardingDocumentReviewQueueItem], int]:
    """List clean employee documents awaiting review in this tenant."""
    if context.roles.isdisjoint(_DOCUMENT_REVIEW_ROLES):
        raise OnboardingAccessDeniedError(
            "Only People Operations and workspace admins can review onboarding documents."
        )

    filters = [
        OnboardingTaskDocument.tenant_id == context.tenant_id,
        OnboardingTaskDocument.status == OnboardingTaskDocumentStatus.AVAILABLE,
        OnboardingTaskDocument.review_status
        == OnboardingTaskDocumentReviewStatus.PENDING_REVIEW,
        OnboardingTask.requires_document_review.is_(True),
        OnboardingTask.status.not_in(
            {OnboardingTaskStatus.COMPLETED, OnboardingTaskStatus.CANCELLED}
        ),
        OnboardingInstance.tenant_id == context.tenant_id,
        OnboardingInstance.status == OnboardingInstanceStatus.ACTIVE,
        Application.tenant_id == context.tenant_id,
        Candidate.tenant_id == context.tenant_id,
        Employee.tenant_id == context.tenant_id,
    ]
    if query and query.strip():
        search_term = f"%{query.strip()}%"
        filters.append(
            or_(
                Candidate.full_name.ilike(search_term),
                Employee.job_title.ilike(search_term),
                OnboardingTask.title.ilike(search_term),
                OnboardingTaskDocument.original_filename.ilike(search_term),
            )
        )

    statement = (
        select(
            OnboardingTaskDocument,
            OnboardingTask.id,
            OnboardingInstance.id,
            Application.id,
            OnboardingTask.title,
            Candidate.full_name,
            Employee.job_title,
        )
        .select_from(OnboardingTaskDocument)
        .join(
            OnboardingTask,
            and_(
                OnboardingTask.id == OnboardingTaskDocument.onboarding_task_id,
                OnboardingTask.tenant_id == OnboardingTaskDocument.tenant_id,
            ),
        )
        .join(
            OnboardingInstance,
            and_(
                OnboardingInstance.id == OnboardingTask.onboarding_instance_id,
                OnboardingInstance.tenant_id == OnboardingTask.tenant_id,
            ),
        )
        .join(
            Application,
            and_(
                Application.id == OnboardingInstance.application_id,
                Application.tenant_id == OnboardingInstance.tenant_id,
            ),
        )
        .join(
            Candidate,
            and_(
                Candidate.id == Application.candidate_id,
                Candidate.tenant_id == Application.tenant_id,
            ),
        )
        .join(
            Employee,
            and_(
                Employee.application_id == Application.id,
                Employee.tenant_id == Application.tenant_id,
            ),
        )
        .where(*filters)
    )
    total = await session.scalar(
        select(func.count()).select_from(
            statement.with_only_columns(
                OnboardingTaskDocument.id,
                maintain_column_froms=True,
            ).subquery()
        )
    )
    result = await session.execute(
        statement
        .order_by(
            OnboardingTaskDocument.uploaded_at.asc().nullslast(),
            OnboardingTaskDocument.created_at,
            OnboardingTaskDocument.id,
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = [
        OnboardingDocumentReviewQueueItem(
            document=document,
            onboarding_task_id=task_id,
            onboarding_instance_id=instance_id,
            application_id=application_id,
            task_title=task_title,
            employee_name=employee_name,
            job_title=job_title,
        )
        for (
            document,
            task_id,
            instance_id,
            application_id,
            task_title,
            employee_name,
            job_title,
        ) in result.all()
    ]
    return items, total or 0


async def create_employee_task_document_upload_intent(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
    command: CreateOnboardingTaskDocumentCommand,
) -> OnboardingTaskDocument:
    """Create a pending upload only for the authenticated employee's open step."""
    async with transactional(session):
        task, _instance = await _load_employee_task(
            session,
            context=context,
            onboarding_task_id=onboarding_task_id,
            lock=True,
        )
        await _require_uploadable_task(session, task=task)

        document_count = await session.scalar(
            select(func.count(OnboardingTaskDocument.id)).where(
                OnboardingTaskDocument.tenant_id == context.tenant_id,
                OnboardingTaskDocument.onboarding_task_id == task.id,
            )
        )
        if document_count is not None and document_count >= _MAX_DOCUMENTS_PER_TASK:
            raise OnboardingValidationError(
                "This task has reached its document upload limit. Contact People Operations."
            )

        document_id = uuid4()
        document = OnboardingTaskDocument(
            id=document_id,
            tenant_id=context.tenant_id,
            onboarding_task_id=task.id,
            storage_key=onboarding_task_document_object_key(
                tenant_id=context.tenant_id,
                onboarding_task_id=task.id,
                document_id=document_id,
            ),
            original_filename=command.original_filename,
            declared_content_type=command.declared_content_type,
            expected_byte_size=command.expected_byte_size,
            checksum_sha256=command.checksum_sha256,
            status=OnboardingTaskDocumentStatus.PENDING_UPLOAD,
            created_by_subject=context.subject,
        )
        session.add(document)
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="onboarding_task_document.upload_intent_created",
            entity_type="onboarding_task_document",
            entity_id=str(document.id),
            details={
                "onboarding_task_id": str(task.id),
                "expected_byte_size": document.expected_byte_size,
                "content_type": document.declared_content_type,
            },
        )
    return document


async def create_employee_task_document_upload_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
) -> PresignedUpload:
    """Authorize a short-lived upload for an employee's pending document."""
    document = await _get_employee_owned_document(
        session,
        context=context,
        document_id=document_id,
        require_uploadable_task=True,
    )
    if document.status is not OnboardingTaskDocumentStatus.PENDING_UPLOAD:
        raise OnboardingValidationError("This document is no longer awaiting upload.")
    try:
        return await storage.create_presigned_upload(
            object_key=document.storage_key,
            content_type=document.declared_content_type,
            checksum_sha256=document.checksum_sha256,
            expires_in=expires_in,
        )
    except ObjectStorageError as error:
        raise OnboardingDocumentStorageError from error


async def confirm_employee_task_document_upload(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
) -> OnboardingTaskDocument:
    """Verify the uploaded object and enqueue malware scanning."""
    async with transactional(session):
        document = await _get_employee_owned_document(
            session,
            context=context,
            document_id=document_id,
            require_uploadable_task=True,
            lock=True,
        )
        if document.status is not OnboardingTaskDocumentStatus.PENDING_UPLOAD:
            raise OnboardingValidationError(
                "Document upload cannot be confirmed in its current state."
            )
        try:
            metadata = await storage.get_object_metadata(
                object_key=document.storage_key,
            )
        except ObjectStorageError as error:
            raise OnboardingDocumentStorageError from error

        if not _metadata_matches(document, metadata):
            document.status = OnboardingTaskDocumentStatus.REJECTED
            record_audit_event(
                session,
                context=context,
                action="onboarding_task_document.upload_rejected",
                entity_type="onboarding_task_document",
                entity_id=str(document.id),
                details={"reason": "metadata_mismatch"},
            )
        else:
            document.status = OnboardingTaskDocumentStatus.UPLOADED
            document.uploaded_at = datetime.now(UTC)
            enqueue_outbox_event(
                session,
                context=context,
                event_type="onboarding_task_document.scan_requested",
                aggregate_type="onboarding_task_document",
                aggregate_id=str(document.id),
                deduplication_key=f"onboarding_task_document.scan_requested:{document.id}",
                payload={"document_id": str(document.id)},
            )
            record_audit_event(
                session,
                context=context,
                action="onboarding_task_document.upload_confirmed",
                entity_type="onboarding_task_document",
                entity_id=str(document.id),
                details={
                    "onboarding_task_id": str(document.onboarding_task_id),
                    "expected_byte_size": document.expected_byte_size,
                    "content_type": document.declared_content_type,
                },
            )
        await session.flush()
        await session.refresh(document)
    return document


async def list_onboarding_task_documents(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
) -> tuple[OnboardingTaskDocument, ...]:
    """List safe metadata for staff or the employee who owns the task."""
    task = await session.scalar(
        select(OnboardingTask).where(
            OnboardingTask.id == onboarding_task_id,
            OnboardingTask.tenant_id == context.tenant_id,
        )
    )
    if task is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    if context.roles.isdisjoint(_DOCUMENT_ACCESS_ROLES):
        await _require_employee_task_owner(
            session,
            context=context,
            task=task,
        )
    return await _list_task_documents(session, context.tenant_id, (task.id,))


async def list_documents_for_authorized_tasks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    task_ids: tuple[UUID, ...],
) -> dict[UUID, tuple[OnboardingTaskDocument, ...]]:
    """Batch-load documents for tasks already authorized by their parent query."""
    if not task_ids:
        return {}
    rows = await session.scalars(
        select(OnboardingTaskDocument)
        .where(
            OnboardingTaskDocument.tenant_id == tenant_id,
            OnboardingTaskDocument.onboarding_task_id.in_(task_ids),
        )
        .order_by(
            desc(OnboardingTaskDocument.created_at),
            desc(OnboardingTaskDocument.id),
        )
    )
    documents_by_task: dict[UUID, list[OnboardingTaskDocument]] = {}
    for document in rows:
        documents_by_task.setdefault(document.onboarding_task_id, []).append(document)
    return {
        task_id: tuple(documents)
        for task_id, documents in documents_by_task.items()
    }


async def create_onboarding_task_document_access_authorization(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    storage: ObjectStorage,
    expires_in: timedelta,
    preview: bool,
) -> PresignedDownload:
    """Create short-lived access only after malware scanning marks a file clean."""
    document = await _get_document_for_authorized_caller(
        session,
        context=context,
        document_id=document_id,
    )
    if document.status is not OnboardingTaskDocumentStatus.AVAILABLE:
        raise OnboardingValidationError(
            "This document is not available until its security scan is complete."
        )
    if preview and document.declared_content_type != "application/pdf":
        raise OnboardingValidationError("Only PDF documents can be previewed.")
    try:
        authorize = (
            storage.create_presigned_preview
            if preview
            else storage.create_presigned_download
        )
        return await authorize(
            object_key=document.storage_key,
            filename=document.original_filename,
            content_type=document.declared_content_type,
            expires_in=expires_in,
        )
    except ObjectStorageError as error:
        raise OnboardingDocumentStorageError from error


async def get_onboarding_task_document_for_worker(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
) -> OnboardingTaskDocument:
    """Load one tenant document for the trusted malware-scanning worker."""
    document = await session.scalar(
        select(OnboardingTaskDocument).where(
            OnboardingTaskDocument.id == document_id,
            OnboardingTaskDocument.tenant_id == tenant_id,
        )
    )
    if document is None:
        raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
    return document


async def begin_onboarding_task_document_scan(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
) -> OnboardingTaskDocument:
    """Set the document to scanning, allowing retry of an interrupted scan."""
    async with transactional(session):
        document = await session.scalar(
            select(OnboardingTaskDocument)
            .where(
                OnboardingTaskDocument.id == document_id,
                OnboardingTaskDocument.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if document is None:
            raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
        if document.status is OnboardingTaskDocumentStatus.UPLOADED:
            document.status = OnboardingTaskDocumentStatus.SCANNING
            document.scan_started_at = datetime.now(UTC)
            record_audit_event(
                session,
                context=context,
                action="onboarding_task_document.scan_started",
                entity_type="onboarding_task_document",
                entity_id=str(document.id),
                details={"onboarding_task_id": str(document.onboarding_task_id)},
            )
        elif document.status is not OnboardingTaskDocumentStatus.SCANNING:
            raise OnboardingValidationError(
                "Document is not ready for malware scanning."
            )
        await session.flush()
    return document


async def complete_onboarding_task_document_scan(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    result: MalwareScanResult,
) -> OnboardingTaskDocument:
    """Persist the scan result without exposing malware details to the UI."""
    async with transactional(session):
        document = await session.scalar(
            select(OnboardingTaskDocument)
            .where(
                OnboardingTaskDocument.id == document_id,
                OnboardingTaskDocument.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if document is None:
            raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
        if document.status is not OnboardingTaskDocumentStatus.SCANNING:
            raise OnboardingValidationError("Document scan is not active.")
        now = datetime.now(UTC)
        document.scan_completed_at = now
        if result.verdict is MalwareScanVerdict.CLEAN:
            document.status = OnboardingTaskDocumentStatus.AVAILABLE
            requires_review = await session.scalar(
                select(OnboardingTask.requires_document_review).where(
                    OnboardingTask.id == document.onboarding_task_id,
                    OnboardingTask.tenant_id == context.tenant_id,
                )
            )
            document.review_status = (
                OnboardingTaskDocumentReviewStatus.PENDING_REVIEW
                if requires_review
                else OnboardingTaskDocumentReviewStatus.NOT_REQUIRED
            )
            if requires_review:
                await enqueue_notifications_for_roles(
                    session,
                    context=context,
                    roles=_DOCUMENT_REVIEW_ROLES,
                    notification_event_type=(
                        NotificationEventType.ONBOARDING_DOCUMENT_REVIEW_REQUESTED
                    ),
                    entity_type="onboarding_task_document",
                    entity_id=document.id,
                    template_key="onboarding_document_review_requested",
                )
            audit_action = "onboarding_task_document.scan_clean"
        else:
            document.status = OnboardingTaskDocumentStatus.QUARANTINED
            audit_action = "onboarding_task_document.scan_infected"
        record_audit_event(
            session,
            context=context,
            action=audit_action,
            entity_type="onboarding_task_document",
            entity_id=str(document.id),
            details={
                "onboarding_task_id": str(document.onboarding_task_id),
                "scanner_name": result.scanner_name,
            },
        )
        await session.flush()
    return document


async def review_onboarding_task_document(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    command: ReviewOnboardingTaskDocumentCommand,
) -> OnboardingTaskDocument:
    """Accept a clean document or request a replacement from the employee."""
    if context.roles.isdisjoint(_DOCUMENT_REVIEW_ROLES):
        raise OnboardingAccessDeniedError(
            "Only People Operations and workspace admins can review onboarding documents."
        )

    async with transactional(session):
        document = await session.scalar(
            select(OnboardingTaskDocument)
            .where(
                OnboardingTaskDocument.id == document_id,
                OnboardingTaskDocument.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if document is None:
            raise OnboardingTaskNotFoundError(
                "Onboarding task document was not found."
            )

        task = await session.scalar(
            select(OnboardingTask)
            .where(
                OnboardingTask.id == document.onboarding_task_id,
                OnboardingTask.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if task is None:
            raise OnboardingTaskNotFoundError(
                "Onboarding task document was not found."
            )
        if (
            task.status
            in {OnboardingTaskStatus.COMPLETED, OnboardingTaskStatus.CANCELLED}
            or document.status is not OnboardingTaskDocumentStatus.AVAILABLE
            or document.review_status
            is not OnboardingTaskDocumentReviewStatus.PENDING_REVIEW
        ):
            raise OnboardingValidationError(
                "Only clean documents awaiting review on an open task can be reviewed."
            )
        if not task.requires_document_review:
            raise OnboardingValidationError(
                "This onboarding task does not require document review."
            )
        if document.version != command.expected_document_version:
            raise OnboardingVersionConflictError(
                "This document changed after it was loaded. Refresh before reviewing it."
            )

        now = datetime.now(UTC)
        document.review_status = (
            OnboardingTaskDocumentReviewStatus.ACCEPTED
            if command.decision is OnboardingTaskDocumentReviewDecision.ACCEPTED
            else OnboardingTaskDocumentReviewStatus.CHANGES_REQUESTED
        )
        document.reviewed_by_subject = context.subject
        document.reviewed_at = now
        document.review_comment = command.comment
        audit_action = (
            "onboarding_task_document.accepted"
            if command.decision is OnboardingTaskDocumentReviewDecision.ACCEPTED
            else "onboarding_task_document.changes_requested"
        )
        record_audit_event(
            session,
            context=context,
            action=audit_action,
            entity_type="onboarding_task_document",
            entity_id=str(document.id),
            details={
                "onboarding_task_id": str(task.id),
            },
        )
        employee_user_id = await session.scalar(
            select(Employee.user_id)
            .join(
                OnboardingInstance,
                OnboardingInstance.application_id == Employee.application_id,
            )
            .where(
                Employee.tenant_id == context.tenant_id,
                OnboardingInstance.id == task.onboarding_instance_id,
                OnboardingInstance.tenant_id == context.tenant_id,
            )
        )
        if employee_user_id is not None:
            accepted = (
                command.decision is OnboardingTaskDocumentReviewDecision.ACCEPTED
            )
            enqueue_notification_request(
                session,
                context=context,
                recipient_user_id=employee_user_id,
                notification_event_type=(
                    NotificationEventType.ONBOARDING_DOCUMENT_ACCEPTED
                    if accepted
                    else NotificationEventType.ONBOARDING_DOCUMENT_CHANGES_REQUESTED
                ),
                entity_type="onboarding_task_document",
                entity_id=document.id,
                template_key=(
                    "onboarding_document_accepted"
                    if accepted
                    else "onboarding_document_changes_requested"
                ),
            )
        await session.flush()
        await session.refresh(document)
    return document


async def _get_employee_owned_document(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
    require_uploadable_task: bool,
    lock: bool = False,
) -> OnboardingTaskDocument:
    """Resolve a document through the caller's own linked employee record."""
    query = select(OnboardingTaskDocument).where(
        OnboardingTaskDocument.id == document_id,
        OnboardingTaskDocument.tenant_id == context.tenant_id,
    )
    if lock:
        query = query.with_for_update()
    document = await session.scalar(query)
    if document is None:
        raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
    task, _instance = await _load_employee_task(
        session,
        context=context,
        onboarding_task_id=document.onboarding_task_id,
        lock=lock,
    )
    if require_uploadable_task:
        await _require_uploadable_task(session, task=task)
    if document.created_by_subject != context.subject:
        raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
    return document


async def _get_document_for_authorized_caller(
    session: AsyncSession,
    *,
    context: TenantContext,
    document_id: UUID,
) -> OnboardingTaskDocument:
    """Resolve a tenant file for workspace staff or its employee owner."""
    document = await session.scalar(
        select(OnboardingTaskDocument).where(
            OnboardingTaskDocument.id == document_id,
            OnboardingTaskDocument.tenant_id == context.tenant_id,
        )
    )
    if document is None:
        raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
    if context.roles.isdisjoint(_DOCUMENT_ACCESS_ROLES):
        task = await session.scalar(
            select(OnboardingTask).where(
                OnboardingTask.id == document.onboarding_task_id,
                OnboardingTask.tenant_id == context.tenant_id,
            )
        )
        if task is None:
            raise OnboardingTaskNotFoundError("Onboarding task document was not found.")
        await _require_employee_task_owner(
            session,
            context=context,
            task=task,
        )
    return document


async def _load_employee_task(
    session: AsyncSession,
    *,
    context: TenantContext,
    onboarding_task_id: UUID,
    lock: bool,
) -> tuple[OnboardingTask, OnboardingInstance]:
    """Load a task only when it belongs to the verified employee's application."""
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user_id is None:
        raise EmployeePortalRecordNotFoundError("Employee record was not found.")
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == context.tenant_id,
            Employee.user_id == user_id,
            Employee.status != EmployeeStatus.INACTIVE,
        )
    )
    if employee is None:
        raise EmployeePortalRecordNotFoundError("Employee record was not found.")

    query = (
        select(OnboardingTask, OnboardingInstance)
        .join(
            OnboardingInstance,
            (OnboardingInstance.id == OnboardingTask.onboarding_instance_id)
            & (OnboardingInstance.tenant_id == OnboardingTask.tenant_id),
        )
        .where(
            OnboardingTask.id == onboarding_task_id,
            OnboardingTask.tenant_id == context.tenant_id,
            OnboardingInstance.application_id == employee.application_id,
        )
    )
    if lock:
        query = query.with_for_update(of=OnboardingTask)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    task, instance = row
    await _require_employee_task_owner(session, context=context, task=task)
    return task, instance


async def _require_employee_task_owner(
    session: AsyncSession,
    *,
    context: TenantContext,
    task: OnboardingTask,
) -> None:
    """Hide task existence unless this is the employee's own task."""
    if task.responsible_party is not OnboardingTaskResponsibility.EMPLOYEE:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    task_application_id = await session.scalar(
        select(OnboardingInstance.application_id).where(
            OnboardingInstance.id == task.onboarding_instance_id,
            OnboardingInstance.tenant_id == context.tenant_id,
        )
    )
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )
    if user_id is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    owns_task = await session.scalar(
        select(Employee.id).where(
            Employee.tenant_id == context.tenant_id,
            Employee.user_id == user_id,
            Employee.application_id == task_application_id,
            Employee.status != EmployeeStatus.INACTIVE,
        )
    )
    if owns_task is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")


async def _require_uploadable_task(
    session: AsyncSession,
    *,
    task: OnboardingTask,
) -> None:
    """Enforce active plan, task configuration, and ordered-step rules."""
    if not task.requires_document_upload:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    instance = await session.scalar(
        select(OnboardingInstance).where(
            OnboardingInstance.id == task.onboarding_instance_id,
            OnboardingInstance.tenant_id == task.tenant_id,
        )
    )
    if instance is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    if (
        instance.status is not OnboardingInstanceStatus.ACTIVE
        or task.status
        not in {OnboardingTaskStatus.NOT_STARTED, OnboardingTaskStatus.IN_PROGRESS}
    ):
        raise OnboardingValidationError(
            "This onboarding step is not currently accepting a document."
        )
    position = await session.scalar(
        select(OnboardingTemplateTask.position).where(
            OnboardingTemplateTask.id == task.template_task_id,
        )
    )
    if position is None:
        raise OnboardingTaskNotFoundError("Onboarding task was not found.")
    earlier_incomplete_id = await session.scalar(
        select(OnboardingTask.id)
        .join(
            OnboardingTemplateTask,
            OnboardingTemplateTask.id == OnboardingTask.template_task_id,
        )
        .where(
            OnboardingTask.tenant_id == task.tenant_id,
            OnboardingTask.onboarding_instance_id == task.onboarding_instance_id,
            OnboardingTemplateTask.position < position,
            OnboardingTask.status != OnboardingTaskStatus.COMPLETED,
        )
        .limit(1)
    )
    if earlier_incomplete_id is not None:
        raise OnboardingValidationError(
            "Complete the earlier onboarding steps before uploading this document."
        )


async def _list_task_documents(
    session: AsyncSession,
    tenant_id: UUID,
    task_ids: tuple[UUID, ...],
) -> tuple[OnboardingTaskDocument, ...]:
    if not task_ids:
        return ()
    return tuple(
        await session.scalars(
            select(OnboardingTaskDocument)
            .where(
                OnboardingTaskDocument.tenant_id == tenant_id,
                OnboardingTaskDocument.onboarding_task_id.in_(task_ids),
            )
            .order_by(
                desc(OnboardingTaskDocument.created_at),
                desc(OnboardingTaskDocument.id),
            )
        )
    )


def _metadata_matches(
    document: OnboardingTaskDocument,
    metadata: StoredObjectMetadata,
) -> bool:
    """Compare provider-verified content metadata to the upload intent."""
    return (
        metadata.content_type == document.declared_content_type
        and metadata.byte_size == document.expected_byte_size
        and metadata.checksum_sha256 == document.checksum_sha256
    )
