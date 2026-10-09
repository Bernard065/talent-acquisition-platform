"""Exceptions raised by requisition approval services."""


class ApprovalPolicyNotFoundError(LookupError):
    """Raised when an approval policy is absent from the caller's tenant."""


class ApprovalPolicyInvalidError(ValueError):
    """Raised when a policy cannot be safely used."""


class ApprovalPolicyAccessDeniedError(PermissionError):
    """Raised when a caller cannot access or change approval policy settings."""


class RequisitionApprovalNotFoundError(LookupError):
    """Raised when an approval instance is absent from the caller's tenant."""


class ApprovalDecisionForbiddenError(PermissionError):
    """Raised when the caller is not the assigned approver."""


class ApprovalDecisionAlreadyMadeError(ValueError):
    """Raised when an approval decision is no longer pending."""
