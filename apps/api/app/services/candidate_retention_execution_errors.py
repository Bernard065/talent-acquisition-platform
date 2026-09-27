"""Errors raised by candidate-retention execution workflows."""


class CandidateRetentionExecutionAccessDeniedError(PermissionError):
    """Raised when the caller cannot execute a retention recommendation."""


class CandidateRetentionExecutionNotFoundError(LookupError):
    """Raised when the candidate or review is absent from the caller's tenant."""


class CandidateRetentionExecutionStateError(ValueError):
    """Raised when current candidate or review state blocks execution."""
