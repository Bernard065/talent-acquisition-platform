"""Version 1 candidate document upload workflow endpoints."""

from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db_session,
    get_object_storage,
    get_tenant_context,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.documents import (
    CandidateDocumentConfirmUploadRequest,
    CandidateDocumentCreateRequest,
    CandidateDocumentDownloadAuthorizationResponse,
    CandidateDocumentResponse,
    CandidateDocumentUploadAuthorizationRequest,
    CandidateDocumentUploadAuthorizationResponse,
)
from app.core.authorization import TenantContext
from app.core.config import Settings
from app.services.candidate_documents import (
    CreateCandidateDocumentUploadIntentCommand,
    confirm_candidate_document_upload,
    create_candidate_document_upload_intent,
    create_document_download_authorization,
    create_document_preview_authorization,
    create_upload_authorization,
    get_candidate_document,
    list_candidate_documents,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.object_storage import ObjectStorage

router = APIRouter(prefix="/candidate-documents", tags=["Candidate Documents"])
_DOWNLOAD_AUTHORIZATION_LIFETIME = timedelta(minutes=5)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
DocumentStorage = Annotated[ObjectStorage, Depends(get_object_storage)]


@router.get(
    "",
    response_model=list[CandidateDocumentResponse],
    summary="List documents for a candidate",
)
async def list_candidate_documents_endpoint(
    candidate_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> list[CandidateDocumentResponse]:
    """Return safe document metadata for an active tenant-owned candidate."""
    documents = await list_candidate_documents(
        session,
        context=context,
        candidate_id=candidate_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return [CandidateDocumentResponse.model_validate(document) for document in documents]


@router.get(
    "/{document_id}/download-authorizations",
    response_model=CandidateDocumentDownloadAuthorizationResponse,
    summary="Create a short-lived document download authorization",
)
async def create_document_download_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    response: Response,
) -> CandidateDocumentDownloadAuthorizationResponse:
    """Issue a short-lived private download URL for a clean scanned document."""
    download = await create_document_download_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=_DOWNLOAD_AUTHORIZATION_LIFETIME,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return CandidateDocumentDownloadAuthorizationResponse(
        url=download.url,
        expires_at=download.expires_at,
    )


@router.get(
    "/{document_id}/preview-authorizations",
    response_model=CandidateDocumentDownloadAuthorizationResponse,
    summary="Create a short-lived document preview authorization",
)
async def create_document_preview_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    response: Response,
) -> CandidateDocumentDownloadAuthorizationResponse:
    """Issue an inline preview URL for a clean, tenant-owned PDF document."""
    preview = await create_document_preview_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=_DOWNLOAD_AUTHORIZATION_LIFETIME,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return CandidateDocumentDownloadAuthorizationResponse(
        url=preview.url,
        expires_at=preview.expires_at,
    )


def _private_idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Return a durable write result without allowing PII-related caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.post(
    "",
    response_model=CandidateDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a candidate document upload intent",
)
async def create_candidate_document_endpoint(
    payload: CandidateDocumentCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create a durable pending document record with a server-owned object key."""

    async def operation() -> tuple[int, dict[str, Any]]:
        document = await create_candidate_document_upload_intent(
            session,
            context=context,
            command=CreateCandidateDocumentUploadIntentCommand(
                candidate_id=payload.candidate_id,
                original_filename=payload.original_filename,
                declared_content_type=payload.declared_content_type,
                expected_byte_size=payload.expected_byte_size,
                checksum_sha256=payload.checksum_sha256,
            ),
        )

        return (
            status.HTTP_201_CREATED,
            CandidateDocumentResponse.model_validate(document).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate_document.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )

    return _private_idempotency_response(result)


@router.get(
    "/{document_id}",
    response_model=CandidateDocumentResponse,
    summary="Get candidate document metadata",
)
async def get_candidate_document_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> CandidateDocumentResponse:
    """Return safe metadata for one tenant-owned candidate document."""
    document = await get_candidate_document(
        session,
        context=context,
        document_id=document_id,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return CandidateDocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/upload-authorizations",
    response_model=CandidateDocumentUploadAuthorizationResponse,
    summary="Create a fresh direct-upload authorization",
)
async def create_upload_authorization_endpoint(
    document_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    response: Response,
    _: Annotated[CandidateDocumentUploadAuthorizationRequest, Body(...)],
) -> CandidateDocumentUploadAuthorizationResponse:
    """Issue a fresh, short-lived URL; never replay it through idempotency."""
    settings: Settings = request.app.state.settings

    upload = await create_upload_authorization(
        session,
        context=context,
        document_id=document_id,
        storage=storage,
        expires_in=timedelta(
            seconds=settings.s3_presigned_upload_expiry_seconds
        ),
    )

    response.headers["Cache-Control"] = "private, no-store"

    return CandidateDocumentUploadAuthorizationResponse(
        upload_url=upload.url,
        required_headers=dict(upload.required_headers),
        expires_at=upload.expires_at,
    )


@router.post(
    "/{document_id}/confirm-upload",
    response_model=CandidateDocumentResponse,
    summary="Confirm and verify a candidate document upload",
)
async def confirm_candidate_document_upload_endpoint(
    document_id: UUID,
    payload: CandidateDocumentConfirmUploadRequest,
    context: CallerContext,
    session: DatabaseSession,
    storage: DocumentStorage,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Verify object metadata and update the document lifecycle atomically."""

    async def operation() -> tuple[int, dict[str, Any]]:
        document = await confirm_candidate_document_upload(
            session,
            context=context,
            document_id=document_id,
            storage=storage,
        )

        return (
            status.HTTP_200_OK,
            CandidateDocumentResponse.model_validate(document).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="candidate_document.confirm_upload",
        payload={
            "document_id": str(document_id),
            **payload.model_dump(mode="json"),
        },
        operation=operation,
    )

    return _private_idempotency_response(result)
