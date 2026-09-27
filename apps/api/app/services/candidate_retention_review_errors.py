"""Errors for candidate-level human retention review evidence."""


class CandidateRetentionReviewAccessDeniedError(PermissionError):
    """Raised when the caller cannot record or inspect retention review evidence."""


class CandidateRetentionReviewNotFoundError(LookupError):
    """Raised when a candidate or active policy is absent from the caller's tenant."""


class CandidateRetentionReviewStateError(ValueError):
    """Raised when the candidate state blocks a requested review disposition."""


class CandidateRetentionReviewValidationError(ValueError):
    """Raised when review timestamps, checklist, or reason codes are invalid."""


class InvalidCandidateRetentionReviewCursorError(ValueError):
    """Raised when a candidate retention-review cursor is malformed or misplaced."""
