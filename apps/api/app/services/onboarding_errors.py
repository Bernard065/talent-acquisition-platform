"""Exceptions raised by onboarding application services."""


class OnboardingAccessDeniedError(PermissionError):
    """Raised when the caller lacks onboarding operational authority."""


class OnboardingTemplateNotFoundError(LookupError):
    """Raised when a template is absent from the caller's tenant."""


class OnboardingInstanceNotFoundError(LookupError):
    """Raised when an onboarding instance is absent from the caller's tenant."""


class OnboardingTaskNotFoundError(LookupError):
    """Raised when an onboarding task is absent from the caller's tenant."""


class OnboardingAlreadyExistsError(ValueError):
    """Raised when an application already has an onboarding instance."""


class OnboardingValidationError(ValueError):
    """Raised when onboarding input or workflow preconditions are invalid."""


class OnboardingVersionConflictError(ValueError):
    """Raised when a caller acts on a stale instance or task version."""
