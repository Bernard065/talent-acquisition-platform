"""Exceptions raised by candidate document workflow services."""

from app.services.candidate_errors import CandidateAccessDeniedError


class CandidateDocumentAccessDeniedError(CandidateAccessDeniedError):
    """Raised when a caller lacks permission to access candidate documents."""


class CandidateDocumentNotFoundError(LookupError):
    """Raised when a document is absent from the caller's tenant."""


class CandidateDocumentNotUploadableError(ValueError):
    """Raised when a document cannot receive an upload authorization."""


class CandidateDocumentVerificationError(RuntimeError):
    """Raised when object storage cannot verify an uploaded document."""
