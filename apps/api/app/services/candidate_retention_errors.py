"""Errors raised while managing candidate-retention policy versions."""


class CandidateRetentionAccessDeniedError(PermissionError):
    """Raised when the caller lacks tenant policy-management privileges."""


class CandidateRetentionPolicyNotFoundError(LookupError):
    """Raised when a policy is absent from the caller's tenant."""


class CandidateRetentionPolicyStateError(ValueError):
    """Raised when a policy lifecycle operation is invalid."""


class CandidateRetentionHoldActiveError(RuntimeError):
    """Raised when an active retention hold blocks candidate erasure."""


class CandidateRetentionHoldStateError(ValueError):
    """Raised when a hold cannot be placed for the candidate's privacy state."""


class CandidateRetentionHoldNotFoundError(LookupError):
    """Raised when a hold is absent from the caller's tenant."""
