"""Exceptions raised by candidate document scanning lifecycle services."""


class CandidateDocumentNotScannableError(ValueError):
    """Raised when a document is not ready to begin malware scanning."""


class CandidateDocumentScanNotFoundError(LookupError):
    """Raised when a scan attempt is absent from the worker tenant."""


class CandidateDocumentScanAlreadyCompletedError(ValueError):
    """Raised when a worker attempts to complete an already finished scan."""
