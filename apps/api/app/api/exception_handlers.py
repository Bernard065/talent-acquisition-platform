"""HTTP exception handlers for the API."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.domains.requisitions.transitions import InvalidRequisitionTransition
from app.services.approval_errors import (
    ApprovalDecisionAlreadyMadeError,
    ApprovalDecisionForbiddenError,
    ApprovalPolicyInvalidError,
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
    SelfApprovalNotAllowedError,
)
from app.services.candidate_document_errors import (
    CandidateDocumentAccessDeniedError,
    CandidateDocumentNotFoundError,
    CandidateDocumentNotUploadableError,
    CandidateDocumentVerificationError,
)
from app.services.candidate_errors import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    CandidateAccessDeniedError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
    RequisitionNotAcceptingApplicationsError,
)
from app.services.idempotency import (
    IdempotencyKeyReuseError,
    InvalidIdempotencyKeyError,
)
from app.services.outbox_inspection_errors import (
    InvalidOutboxCursorError,
    OutboxInspectionAccessDeniedError,
)
from app.services.requisition_errors import (
    InvalidRequisitionCursorError,
    RequisitionAccessDeniedError,
    RequisitionNotEditableError,
    RequisitionNotFoundError,
)

logger = structlog.get_logger()


def _error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> JSONResponse:
    """Build a consistent API error response."""
    request_id = request.headers.get("X-Request-ID", "unknown")

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "request_id": request_id,
        },
    )


async def not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle resources that cannot be found."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Requisition not found.",
    )


async def candidate_or_application_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle candidates or applications that cannot be found."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Candidate or application not found.",
    )


async def forbidden(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle insufficient permissions."""
    return _error_response(
        request,
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permission.",
    )


async def conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle conflicts caused by the current requisition state."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="The requisition cannot be changed in its current state.",
    )


async def invalid_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid requisition cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid requisition cursor.",
    )


async def invalid_outbox_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle malformed dead-letter pagination cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid outbox cursor.",
    )


async def invalid_idempotency_key(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid idempotency keys."""
    return _error_response(
        request,
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid Idempotency-Key.",
    )


async def idempotency_key_reused(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle idempotency keys reused for a different request."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency-Key was already used for a different request.",
    )


async def database_unavailable(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Handle database availability errors."""
    logger.error(
        "database_unavailable",
        request_id=request.headers.get("X-Request-ID", "unknown"),
        error_type=type(error).__name__,
    )

    response = _error_response(
        request,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable.",
    )
    response.headers["Retry-After"] = "5"
    return response


async def candidate_document_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide document existence outside the caller's tenant."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Candidate document not found.",
    )


async def document_storage_unavailable(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Return a retryable response without exposing storage-provider details."""
    logger.error(
        "document_storage_unavailable",
        request_id=request.headers.get("X-Request-ID", "unknown"),
        error_type=type(error).__name__,
    )

    response = _error_response(
        request,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Document storage service is temporarily unavailable.",
    )
    response.headers["Retry-After"] = "5"
    return response


def register_exception_handlers(application: FastAPI) -> None:
    """Register application-wide exception handlers."""
    application.add_exception_handler(RequisitionNotFoundError, not_found)
    application.add_exception_handler(RequisitionAccessDeniedError, forbidden)
    application.add_exception_handler(RequisitionNotEditableError, conflict)
    application.add_exception_handler(InvalidRequisitionTransition, conflict)
    application.add_exception_handler(StaleDataError, conflict)
    application.add_exception_handler(InvalidRequisitionCursorError, invalid_cursor)
    application.add_exception_handler(
        InvalidIdempotencyKeyError,
        invalid_idempotency_key,
    )
    application.add_exception_handler(
        IdempotencyKeyReuseError,
        idempotency_key_reused,
    )
    application.add_exception_handler(
        OutboxInspectionAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InvalidOutboxCursorError,
        invalid_outbox_cursor,
    )

    application.add_exception_handler(ApprovalPolicyNotFoundError, not_found)
    application.add_exception_handler(
        RequisitionApprovalNotFoundError,
        not_found,
    )
    application.add_exception_handler(
        ApprovalDecisionForbiddenError,
        forbidden,
    )
    application.add_exception_handler(
        SelfApprovalNotAllowedError,
        forbidden,
    )
    application.add_exception_handler(
        ApprovalDecisionAlreadyMadeError,
        conflict,
    )
    application.add_exception_handler(
        ApprovalPolicyInvalidError,
        conflict,
    )

    application.add_exception_handler(
        CandidateNotFoundError,
        candidate_or_application_not_found,
    )
    application.add_exception_handler(
        ApplicationNotFoundError,
        candidate_or_application_not_found,
    )
    application.add_exception_handler(CandidateAccessDeniedError, forbidden)
    application.add_exception_handler(CandidateAlreadyExistsError, conflict)
    application.add_exception_handler(ApplicationAlreadyExistsError, conflict)
    application.add_exception_handler(
        RequisitionNotAcceptingApplicationsError,
        conflict,
    )

    application.add_exception_handler(
        CandidateDocumentNotFoundError,
        candidate_document_not_found,
    )
    application.add_exception_handler(
        CandidateDocumentAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        CandidateDocumentNotUploadableError,
        conflict,
    )
    application.add_exception_handler(
        CandidateDocumentVerificationError,
        document_storage_unavailable,
    )

    application.add_exception_handler(OperationalError, database_unavailable)
