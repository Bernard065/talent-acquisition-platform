"""Errors for downstream candidate-data deletion tracking."""


class CandidateProcessorDeletionNotFoundError(LookupError):
    """A tenant-scoped processor deletion request does not exist."""


class CandidateProcessorDeletionAccessDeniedError(PermissionError):
    """The caller cannot administer processor deletion outcomes."""


class CandidateProcessorDeletionValidationError(ValueError):
    """A processor deletion status update is invalid."""


class CandidateProcessorDeletionVersionConflictError(RuntimeError):
    """The processor deletion request changed since it was read."""


class CandidateProcessorDeletionLeaseLostError(RuntimeError):
    """A worker no longer owns the processor deletion request lease."""


class CandidateProcessorDisclosureConflictError(RuntimeError):
    """A source operation was associated with conflicting disclosures."""
