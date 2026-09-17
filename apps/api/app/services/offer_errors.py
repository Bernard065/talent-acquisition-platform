"""Exceptions for the offer workflow."""

from app.domains.offers.transitions import InvalidOfferTransitionError


class OfferNotFoundError(LookupError):
    """Raised when an offer is absent from the caller's tenant."""


class OfferAccessDeniedError(PermissionError):
    """Raised when the caller cannot perform an offer operation."""


class OfferValidationError(ValueError):
    """Raised when offer input is invalid."""


class OfferVersionConflictError(ValueError):
    """Raised when the caller acts on an outdated offer version."""


class OfferAlreadyExistsError(ValueError):
    """Raised when an application already has an active offer."""


class OfferApprovalNotFoundError(LookupError):
    """Raised when an offer approval is absent from the caller's tenant."""


class OfferApprovalForbiddenError(PermissionError):
    """Raised when the caller is not the current assigned approver."""


class OfferApprovalAlreadyCompleteError(ValueError):
    """Raised when an approval is no longer pending."""


class OfferSelfApprovalError(PermissionError):
    """Raised when a submitter is configured as an offer approver."""


class OfferApplicationNotEligibleError(ValueError):
    """Raised when an application is not eligible for an offer action."""


class OfferSignatureRequiredError(ValueError):
    """Raised when offer acceptance lacks a completed signature request."""


__all__ = [
    "InvalidOfferTransitionError",
    "OfferAccessDeniedError",
    "OfferAlreadyExistsError",
    "OfferApplicationNotEligibleError",
    "OfferApprovalAlreadyCompleteError",
    "OfferApprovalForbiddenError",
    "OfferApprovalNotFoundError",
    "OfferNotFoundError",
    "OfferSelfApprovalError",
    "OfferSignatureRequiredError",
    "OfferValidationError",
    "OfferVersionConflictError",
]
