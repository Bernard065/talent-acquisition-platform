"""Safe HTTP error mapping for requisition application services."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.domains.requisitions.transitions import InvalidRequisitionTransition
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
    """Create a safe, request-correlated API error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", "unknown"),
        },
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Register application-service exception mappings."""

    async def not_found(
        request: Request,
        _: Exception,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisition not found.",
        )

    async def forbidden(
        request: Request,
        _: Exception,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission.",
        )

    async def conflict(
        request: Request,
        _: Exception,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            detail="The requisition cannot be changed in its current state.",
        )

    async def invalid_cursor(
        request: Request,
        _: Exception,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid requisition cursor.",
        )

    async def database_unavailable(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
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

    application.add_exception_handler(RequisitionNotFoundError, not_found)
    application.add_exception_handler(RequisitionAccessDeniedError, forbidden)
    application.add_exception_handler(RequisitionNotEditableError, conflict)
    application.add_exception_handler(InvalidRequisitionTransition, conflict)
    application.add_exception_handler(StaleDataError, conflict)
    application.add_exception_handler(InvalidRequisitionCursorError, invalid_cursor)
    application.add_exception_handler(OperationalError, database_unavailable)
