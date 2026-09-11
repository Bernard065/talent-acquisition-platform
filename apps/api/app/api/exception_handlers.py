"""HTTP exception handlers for the API."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.domains.applications.transitions import InvalidApplicationTransition
from app.domains.decisions.transitions import InvalidHiringDecisionTransition
from app.domains.interviews.transitions import InvalidInterviewSessionTransition
from app.domains.job_postings.transitions import InvalidJobPostingTransition
from app.domains.offers.transitions import InvalidOfferTransitionError
from app.domains.onboarding.transitions import (
    InvalidOnboardingInstanceTransition,
    InvalidOnboardingTaskTransition,
)
from app.domains.requisitions.transitions import InvalidRequisitionTransition
from app.services.abuse_control import (
    AbuseControlRejectedError,
    AbuseControlUnavailableError,
)
from app.services.application_pipeline_errors import (
    ApplicationPipelineAccessDeniedError,
    ApplicationRejectionReasonError,
    ApplicationVersionConflictError,
)
from app.services.approval_errors import (
    ApprovalDecisionAlreadyMadeError,
    ApprovalDecisionForbiddenError,
    ApprovalPolicyInvalidError,
    ApprovalPolicyNotFoundError,
    RequisitionApprovalNotFoundError,
    SelfApprovalNotAllowedError,
)
from app.services.candidate_document_errors import (
    CandidateDocumentAccessDeniedError,
    CandidateDocumentNotFoundError,
    CandidateDocumentNotUploadableError,
    CandidateDocumentVerificationError,
)
from app.services.candidate_errors import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
    CandidateAccessDeniedError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
    RequisitionNotAcceptingApplicationsError,
)
from app.services.hiring_decision_errors import (
    HiringDecisionAccessDeniedError,
    HiringDecisionAlreadyExistsError,
    HiringDecisionFeedbackRequiredError,
    HiringDecisionSelfDecisionError,
    HiringDecisionValidationError,
    HiringDecisionVersionConflictError,
)
from app.services.idempotency import (
    IdempotencyKeyReuseError,
    InvalidIdempotencyKeyError,
)
from app.services.interview_feedback_errors import (
    InterviewFeedbackAccessDeniedError,
    InterviewFeedbackAlreadyExistsError,
    InterviewFeedbackIncompleteError,
    InterviewFeedbackNotEditableError,
    InterviewFeedbackNotFoundError,
    InterviewFeedbackVersionConflictError,
)
from app.services.interview_lifecycle_errors import (
    InterviewLifecycleAccessDeniedError,
    InterviewLifecycleValidationError,
    InterviewRescheduleConflictError,
    InterviewSessionNotFoundError,
    InterviewSessionVersionConflictError,
)
from app.services.interview_scheduling_errors import (
    InterviewApplicationNotReadyError,
    InterviewParticipantsNotFoundError,
    InterviewScheduleConflictError,
    InterviewSchedulingAccessDeniedError,
    InterviewSchedulingValidationError,
)
from app.services.interview_search_errors import (
    InterviewSearchAccessDeniedError,
    InvalidInterviewSearchCursorError,
)
from app.services.job_posting_errors import (
    InvalidJobPostingCursorError,
    JobPostingAccessDeniedError,
    JobPostingNotFoundError,
    JobPostingRequisitionNotOpenError,
    JobPostingValidationError,
    JobPostingVersionConflictError,
)
from app.services.notification_preference_errors import (
    NotificationPreferenceAccessDeniedError,
    NotificationPreferenceVersionConflictError,
)
from app.services.offer_errors import (
    OfferAccessDeniedError,
    OfferAlreadyExistsError,
    OfferApplicationNotEligibleError,
    OfferApprovalAlreadyCompleteError,
    OfferApprovalForbiddenError,
    OfferApprovalNotFoundError,
    OfferNotFoundError,
    OfferSelfApprovalError,
    OfferValidationError,
    OfferVersionConflictError,
)
from app.services.onboarding_errors import (
    OnboardingAccessDeniedError,
    OnboardingAlreadyExistsError,
    OnboardingInstanceNotFoundError,
    OnboardingTaskNotFoundError,
    OnboardingTemplateNotFoundError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)
from app.services.outbox_inspection_errors import (
    InvalidOutboxCursorError,
    OutboxInspectionAccessDeniedError,
)
from app.services.public_application_errors import (
    PublicApplicationJobNotFoundError,
)
from app.services.public_job_errors import (
    InvalidPublicJobCursorError,
    PublicJobNotFoundError,
)
from app.services.recruiting_search_errors import (
    InvalidRecruitingSearchCursorError,
)
from app.services.requisition_errors import (
    InvalidRequisitionCursorError,
    RequisitionAccessDeniedError,
    RequisitionNotEditableError,
    RequisitionNotFoundError,
)

logger = structlog.get_logger()


def _error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> JSONResponse:
    """Build a consistent API error response."""
    request_id = request.headers.get("X-Request-ID", "unknown")

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "request_id": request_id,
        },
    )


async def not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle resources that cannot be found."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Requisition not found.",
    )


async def candidate_or_application_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle candidates or applications that cannot be found."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Candidate or application not found.",
    )


async def forbidden(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle insufficient permissions."""
    return _error_response(
        request,
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permission.",
    )


async def conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle conflicts caused by the current requisition state."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="The requisition cannot be changed in its current state.",
    )


async def application_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid application workflow state changes."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Application cannot transition in its current state.",
    )


async def application_version_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Require callers to retry against the latest application version."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Application has changed; retrieve the latest version and retry.",
    )


async def invalid_application_transition_request(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle service-level transition input validation failures."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid application transition request.",
    )


async def invalid_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid requisition cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid requisition cursor.",
    )


async def invalid_outbox_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle malformed dead-letter pagination cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid outbox cursor.",
    )


async def invalid_idempotency_key(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid idempotency keys."""
    return _error_response(
        request,
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid Idempotency-Key.",
    )


async def idempotency_key_reused(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle idempotency keys reused for a different request."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency-Key was already used for a different request.",
    )


async def database_unavailable(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Handle database availability errors."""
    logger.error(
        "database_unavailable",
        request_id=request.headers.get("X-Request-ID", "unknown"),
        error_type=type(error).__name__,
    )

    response = _error_response(
        request,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable.",
    )
    response.headers["Retry-After"] = "5"
    return response


async def candidate_document_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide document existence outside the caller's tenant."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Candidate document not found.",
    )


async def document_storage_unavailable(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Return a retryable response without exposing storage-provider details."""
    logger.error(
        "document_storage_unavailable",
        request_id=request.headers.get("X-Request-ID", "unknown"),
        error_type=type(error).__name__,
    )

    response = _error_response(
        request,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Document storage service is temporarily unavailable.",
    )
    response.headers["Retry-After"] = "5"
    return response


async def interview_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide interview-related resources outside the caller's tenant."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Interview application or participant not found.",
    )


async def interview_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle database-enforced double-booking conflicts."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="An interview participant is already booked.",
    )


async def invalid_interview_schedule(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid interview workflow or scheduling input."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid interview scheduling request.",
    )


async def interview_feedback_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide feedback outside its author and tenant scope."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Interview feedback not found.",
    )


async def interview_feedback_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle duplicate drafts and immutable feedback safely."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Interview feedback cannot be changed in its current state.",
    )


async def interview_feedback_version_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Require callers to retrieve the latest feedback before retrying."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Interview feedback has changed; retrieve the latest version and retry.",
    )


async def invalid_interview_feedback(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle incomplete feedback submission safely."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid interview feedback request.",
    )


async def interview_session_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide an interview session outside the caller's tenant."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Interview session not found.",
    )


async def interview_session_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle terminal-state lifecycle operations safely."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Interview session cannot be changed in its current state.",
    )


async def interview_session_version_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Require a caller to retrieve the latest session before retrying."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Interview session has changed; retrieve the latest version and retry.",
    )


async def interview_reschedule_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Map participant double-booking to a safe conflict response."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="An interview participant is already booked.",
    )


async def invalid_interview_lifecycle_request(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid lifecycle request input."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid interview lifecycle request.",
    )


async def hiring_decision_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle an existing final decision safely."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="A final hiring decision already exists for this application.",
    )


async def hiring_decision_version_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Require a decision-maker to use the current application version."""
    return _error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Application has changed; retrieve the latest version and retry.",
    )


async def invalid_hiring_decision(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid decision workflow or request input."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid hiring decision request.",
    )


async def invalid_onboarding_request(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Return a safe validation error for onboarding workflow input."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid onboarding request.",
    )


async def public_job_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide unpublished, expired, closed, and nonexistent postings alike."""
    return _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Job posting not found.",
    )


async def invalid_public_job_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Return a safe validation error for malformed public pagination state."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid public job cursor.",
    )


async def invalid_recruiting_search_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Return a safe validation response for malformed recruiter cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid recruiter search cursor.",
    )


async def interview_search_forbidden(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Reject callers without permission to inspect the interview calendar."""
    return _error_response(
        request,
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permission.",
    )


async def invalid_interview_search_cursor(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Return a safe validation response for malformed calendar cursors."""
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid interview search cursor.",
    )


def _private_error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> JSONResponse:
    """Return a non-cacheable error for tenant-private job-posting APIs."""
    response = _error_response(
        request,
        status_code=status_code,
        detail=detail,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def job_posting_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Hide job postings outside the caller's tenant."""
    return _private_error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Job posting not found.",
    )


async def job_posting_forbidden(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle insufficient job-posting management permissions."""
    return _private_error_response(
        request,
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permission.",
    )


async def job_posting_conflict(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid lifecycle changes and optimistic-lock conflicts."""
    return _private_error_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail="Job posting cannot be changed in its current state.",
    )


async def invalid_job_posting_request(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle invalid job-posting inputs and cursors."""
    return _private_error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Invalid job posting request.",
    )


async def public_application_job_not_found(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Do not reveal hidden, expired, or nonexistent job posting state."""
    response = _error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Job posting not found.",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def public_application_rejected(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Reject failed abuse checks without disclosing provider details."""
    response = _error_response(
        request,
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Application submission could not be accepted.",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def public_application_abuse_unavailable(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Fail safely when the abuse-control provider is unavailable."""
    response = _error_response(
        request,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Application submission service is temporarily unavailable.",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Retry-After"] = "5"
    return response


def register_exception_handlers(application: FastAPI) -> None:
    """Register application-wide exception handlers."""
    application.add_exception_handler(RequisitionNotFoundError, not_found)
    application.add_exception_handler(RequisitionAccessDeniedError, forbidden)
    application.add_exception_handler(RequisitionNotEditableError, conflict)
    application.add_exception_handler(InvalidRequisitionTransition, conflict)
    application.add_exception_handler(
        ApplicationPipelineAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InvalidApplicationTransition,
        application_conflict,
    )
    application.add_exception_handler(
        ApplicationVersionConflictError,
        application_version_conflict,
    )
    application.add_exception_handler(
        ApplicationRejectionReasonError,
        invalid_application_transition_request,
    )
    application.add_exception_handler(StaleDataError, conflict)
    application.add_exception_handler(InvalidRequisitionCursorError, invalid_cursor)
    application.add_exception_handler(
        PublicJobNotFoundError,
        public_job_not_found,
    )
    application.add_exception_handler(
        InvalidPublicJobCursorError,
        invalid_public_job_cursor,
    )
    application.add_exception_handler(
        InvalidRecruitingSearchCursorError,
        invalid_recruiting_search_cursor,
    )
    application.add_exception_handler(
        InterviewSearchAccessDeniedError,
        interview_search_forbidden,
    )
    application.add_exception_handler(
        InvalidInterviewSearchCursorError,
        invalid_interview_search_cursor,
    )
    application.add_exception_handler(
        JobPostingNotFoundError,
        job_posting_not_found,
    )
    application.add_exception_handler(
        JobPostingAccessDeniedError,
        job_posting_forbidden,
    )
    application.add_exception_handler(
        JobPostingVersionConflictError,
        job_posting_conflict,
    )
    application.add_exception_handler(
        JobPostingRequisitionNotOpenError,
        job_posting_conflict,
    )
    application.add_exception_handler(
        InvalidJobPostingTransition,
        job_posting_conflict,
    )
    application.add_exception_handler(
        JobPostingValidationError,
        invalid_job_posting_request,
    )
    application.add_exception_handler(
        InvalidJobPostingCursorError,
        invalid_job_posting_request,
    )
    application.add_exception_handler(
        PublicApplicationJobNotFoundError,
        public_application_job_not_found,
    )
    application.add_exception_handler(
        AbuseControlRejectedError,
        public_application_rejected,
    )
    application.add_exception_handler(
        AbuseControlUnavailableError,
        public_application_abuse_unavailable,
    )
    application.add_exception_handler(
        InvalidIdempotencyKeyError,
        invalid_idempotency_key,
    )
    application.add_exception_handler(
        IdempotencyKeyReuseError,
        idempotency_key_reused,
    )
    application.add_exception_handler(
        OutboxInspectionAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InvalidOutboxCursorError,
        invalid_outbox_cursor,
    )
    application.add_exception_handler(
        NotificationPreferenceAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        NotificationPreferenceVersionConflictError,
        conflict,
    )

    application.add_exception_handler(ApprovalPolicyNotFoundError, not_found)
    application.add_exception_handler(
        RequisitionApprovalNotFoundError,
        not_found,
    )
    application.add_exception_handler(
        ApprovalDecisionForbiddenError,
        forbidden,
    )
    application.add_exception_handler(
        SelfApprovalNotAllowedError,
        forbidden,
    )
    application.add_exception_handler(
        ApprovalDecisionAlreadyMadeError,
        conflict,
    )
    application.add_exception_handler(
        ApprovalPolicyInvalidError,
        conflict,
    )

    application.add_exception_handler(
        CandidateNotFoundError,
        candidate_or_application_not_found,
    )
    application.add_exception_handler(
        ApplicationNotFoundError,
        candidate_or_application_not_found,
    )
    application.add_exception_handler(CandidateAccessDeniedError, forbidden)
    application.add_exception_handler(CandidateAlreadyExistsError, conflict)
    application.add_exception_handler(ApplicationAlreadyExistsError, conflict)
    application.add_exception_handler(
        RequisitionNotAcceptingApplicationsError,
        conflict,
    )

    application.add_exception_handler(
        CandidateDocumentNotFoundError,
        candidate_document_not_found,
    )
    application.add_exception_handler(
        CandidateDocumentAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        CandidateDocumentNotUploadableError,
        conflict,
    )
    application.add_exception_handler(
        CandidateDocumentVerificationError,
        document_storage_unavailable,
    )
    application.add_exception_handler(
        InterviewSchedulingAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InterviewParticipantsNotFoundError,
        interview_not_found,
    )
    application.add_exception_handler(
        InterviewScheduleConflictError,
        interview_conflict,
    )
    application.add_exception_handler(
        InterviewApplicationNotReadyError,
        invalid_interview_schedule,
    )
    application.add_exception_handler(
        InterviewSchedulingValidationError,
        invalid_interview_schedule,
    )
    application.add_exception_handler(
        InterviewFeedbackAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InterviewFeedbackNotFoundError,
        interview_feedback_not_found,
    )
    application.add_exception_handler(
        InterviewFeedbackAlreadyExistsError,
        interview_feedback_conflict,
    )
    application.add_exception_handler(
        InterviewFeedbackNotEditableError,
        interview_feedback_conflict,
    )
    application.add_exception_handler(
        InterviewFeedbackVersionConflictError,
        interview_feedback_version_conflict,
    )
    application.add_exception_handler(
        InterviewFeedbackIncompleteError,
        invalid_interview_feedback,
    )
    application.add_exception_handler(
        InterviewLifecycleAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        InterviewSessionNotFoundError,
        interview_session_not_found,
    )
    application.add_exception_handler(
        InvalidInterviewSessionTransition,
        interview_session_conflict,
    )
    application.add_exception_handler(
        InterviewSessionVersionConflictError,
        interview_session_version_conflict,
    )
    application.add_exception_handler(
        InterviewRescheduleConflictError,
        interview_reschedule_conflict,
    )
    application.add_exception_handler(
        InterviewLifecycleValidationError,
        invalid_interview_lifecycle_request,
    )

    application.add_exception_handler(
        HiringDecisionAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        HiringDecisionSelfDecisionError,
        forbidden,
    )
    application.add_exception_handler(
        HiringDecisionAlreadyExistsError,
        hiring_decision_conflict,
    )
    application.add_exception_handler(
        HiringDecisionVersionConflictError,
        hiring_decision_version_conflict,
    )
    application.add_exception_handler(
        HiringDecisionFeedbackRequiredError,
        invalid_hiring_decision,
    )
    application.add_exception_handler(
        HiringDecisionValidationError,
        invalid_hiring_decision,
    )
    application.add_exception_handler(
        InvalidHiringDecisionTransition,
        invalid_hiring_decision,
    )

    application.add_exception_handler(OfferNotFoundError, not_found)
    application.add_exception_handler(OfferApprovalNotFoundError, not_found)
    application.add_exception_handler(OfferAccessDeniedError, forbidden)
    application.add_exception_handler(OfferApprovalForbiddenError, forbidden)
    application.add_exception_handler(OfferSelfApprovalError, forbidden)
    application.add_exception_handler(OfferAlreadyExistsError, conflict)
    application.add_exception_handler(OfferApprovalAlreadyCompleteError, conflict)
    application.add_exception_handler(OfferVersionConflictError, conflict)
    application.add_exception_handler(OfferApplicationNotEligibleError, conflict)
    application.add_exception_handler(InvalidOfferTransitionError, conflict)
    application.add_exception_handler(OfferValidationError, invalid_hiring_decision)

    application.add_exception_handler(
        OnboardingAccessDeniedError,
        forbidden,
    )
    application.add_exception_handler(
        OnboardingTemplateNotFoundError,
        not_found,
    )
    application.add_exception_handler(
        OnboardingInstanceNotFoundError,
        not_found,
    )
    application.add_exception_handler(
        OnboardingTaskNotFoundError,
        not_found,
    )
    application.add_exception_handler(
        OnboardingAlreadyExistsError,
        conflict,
    )
    application.add_exception_handler(
        OnboardingVersionConflictError,
        conflict,
    )
    application.add_exception_handler(
        InvalidOnboardingInstanceTransition,
        conflict,
    )
    application.add_exception_handler(
        InvalidOnboardingTaskTransition,
        conflict,
    )
    application.add_exception_handler(
        OnboardingValidationError,
        invalid_onboarding_request,
    )

    application.add_exception_handler(OperationalError, database_unavailable)
