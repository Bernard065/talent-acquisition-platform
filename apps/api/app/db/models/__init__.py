"""Database models for tenant identity, audit logging, idempotency, and approvals."""

from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.approval import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    RequisitionApproval,
    RequisitionApprovalDecision,
)
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_document import CandidateDocument
from app.db.models.candidate_document_scan import CandidateDocumentScan
from app.db.models.idempotency import IdempotencyRecord
from app.db.models.identity import Tenant, User, UserRoleAssignment
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition

__all__ = [
    "Application",
    "ApplicationStageHistory",
    "ApprovalPolicy",
    "ApprovalPolicyStep",
    "AuditEvent",
    "Candidate",
    "CandidateDocument",
    "CandidateDocumentScan",
    "IdempotencyRecord",
    "InterviewParticipant",
    "InterviewSession",
    "OutboxEvent",
    "Requisition",
    "RequisitionApproval",
    "RequisitionApprovalDecision",
    "Tenant",
    "User",
    "UserRoleAssignment",
]
