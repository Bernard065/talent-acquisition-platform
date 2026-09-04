"""Exceptions raised by requisition approval services."""


class ApprovalPolicyNotFoundError(LookupError):
    """Raised when an approval policy is absent from the caller's tenant."""


class ApprovalPolicyInvalidError(ValueError):
    """Raised when a policy cannot be safely used."""


class RequisitionApprovalNotFoundError(LookupError):
    """Raised when an approval instance is absent from the caller's tenant."""


class ApprovalDecisionForbiddenError(PermissionError):
    """Raised when the caller is not the assigned approver."""


class ApprovalDecisionAlreadyMadeError(ValueError):
    """Raised when an approval decision is no longer pending."""


class SelfApprovalNotAllowedError(PermissionError):
    """Raised when a submitter is included in the policy approvers."""
