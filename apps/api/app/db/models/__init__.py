"""Database models for tenant identity, audit logging, idempotency, and approvals."""

from app.db.models.application import Application
from app.db.models.application_debrief import (
    ApplicationDebrief,
    ApplicationDecisionHistory,
)
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.approval import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    RequisitionApproval,
    RequisitionApprovalDecision,
)
from app.db.models.audit import AuditEvent
from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.models.candidate_processor import (
    CandidateProcessorDeletionRequest,
    CandidateProcessorDisclosure,
)
from app.db.models.candidate_retention_execution import CandidateRetentionExecution
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.models.candidate_talent_pool_consent import CandidateTalentPoolConsentEvent
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.idempotency import IdempotencyRecord
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.interview_feedback import InterviewFeedback
from app.db.models.interview_session_lifecycle import (
    InterviewSessionLifecycleHistory,
)
from app.db.models.job_posting import JobPosting
from app.db.models.notification import Notification, NotificationPreference
from app.db.models.offer import Offer, OfferLifecycleHistory
from app.db.models.offer_approval import OfferApproval, OfferApprovalDecision
from app.db.models.offer_signature import (
    OfferSignatureHistory,
    OfferSignatureRequest,
)
from app.db.models.offer_signature_callback import (
    OfferSignatureCallbackReceipt,
)
from app.db.models.onboarding import (
    OnboardingInstance,
    OnboardingInstanceHistory,
    OnboardingTask,
    OnboardingTaskHistory,
    OnboardingTemplate,
    OnboardingTemplateTask,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.db.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookSubscription,
)

__all__ = [
    "Application",
    "ApplicationDebrief",
    "ApplicationDecisionHistory",
    "ApplicationStageHistory",
    "ApprovalPolicy",
    "ApprovalPolicyStep",
    "AuditEvent",
    "Candidate",
    "CandidateDocument",
    "CandidateDocumentScan",
    "CandidateProcessorDisclosure",
    "CandidateProcessorDeletionRequest",
    "CandidateRetentionPolicy",
    "CandidateRetentionExecution",
    "CandidateRetentionReview",
    "CandidateTalentPoolConsentEvent",
    "CandidateRetentionHold",
    "CalendarConnection",
    "HrisConnection",
    "HrisHandoff",
    "IdempotencyRecord",
    "InterviewCalendarSync",
    "InterviewFeedback",
    "InterviewParticipant",
    "InterviewSession",
    "InterviewSessionLifecycleHistory",
    "JobPosting",
    "Notification",
    "NotificationPreference",
    "Offer",
    "OfferApproval",
    "OfferApprovalDecision",
    "OfferLifecycleHistory",
    "OfferSignatureHistory",
    "OfferSignatureRequest",
    "OfferSignatureCallbackReceipt",
    "OnboardingInstance",
    "OnboardingInstanceHistory",
    "OnboardingTask",
    "OnboardingTaskHistory",
    "OnboardingTemplate",
    "OnboardingTemplateTask",
    "OutboxEvent",
    "Requisition",
    "RequisitionApproval",
    "RequisitionApprovalDecision",
    "Tenant",
    "User",
    "UserRoleAssignment",
    "WebhookDelivery",
    "WebhookEndpoint",
    "WebhookEvent",
    "WebhookSubscription",
]
