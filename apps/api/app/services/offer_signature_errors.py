"""Exceptions for the tenant-scoped offer signature workflow."""

from app.domains.signatures.transitions import InvalidOfferSignatureTransitionError


class OfferSignatureNotFoundError(LookupError):
    """Raised when a signature request is absent from the caller's tenant."""


class OfferSignatureAccessDeniedError(PermissionError):
    """Raised when the caller lacks offer-signature workflow permission."""


class OfferSignatureValidationError(ValueError):
    """Raised when signature workflow input is invalid."""


class OfferSignatureVersionConflictError(ValueError):
    """Raised when a caller acts on a stale signature request version."""


class OfferSignatureAlreadyExistsError(ValueError):
    """Raised when an offer version already has a signature request."""


class OfferSignatureCallbackVerificationError(ValueError):
    """Raised when a provider callback cannot be cryptographically verified."""


class OfferSignatureCallbackProviderNotConfiguredError(LookupError):
    """Raised when no trusted callback verifier exists for a provider."""


class OfferSignatureCallbackEnvelopeNotFoundError(LookupError):
    """Raised when a verified callback does not match a sent envelope."""


class OfferSignatureCallbackReplayMismatchError(ValueError):
    """Raised when a provider reuses an event ID with different content."""


__all__ = [
    "InvalidOfferSignatureTransitionError",
    "OfferSignatureAccessDeniedError",
    "OfferSignatureAlreadyExistsError",
    "OfferSignatureCallbackEnvelopeNotFoundError",
    "OfferSignatureCallbackProviderNotConfiguredError",
    "OfferSignatureCallbackReplayMismatchError",
    "OfferSignatureCallbackVerificationError",
    "OfferSignatureNotFoundError",
    "OfferSignatureValidationError",
    "OfferSignatureVersionConflictError",
]
