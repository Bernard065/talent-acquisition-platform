"""Controlled values for candidate-level retention review evidence."""

from enum import StrEnum


class CandidateRetentionReviewPurpose(StrEnum):
    """Retention purpose assessed by one human review."""

    UNSUCCESSFUL_APPLICANT = "unsuccessful_applicant"
    WITHDRAWN_APPLICANT = "withdrawn_applicant"
    TALENT_POOL = "talent_pool"
    HIRED_RECRUITING_COPY = "hired_recruiting_copy"


class CandidateRetentionReviewDisposition(StrEnum):
    """Non-destructive result recorded by the reviewer."""

    RETAIN = "retain"
    DEFER = "defer"
    RECOMMEND_MANUAL_ERASURE = "recommend_manual_erasure"


class CandidateRetentionReviewReason(StrEnum):
    """Privacy-safe reason codes; review narratives are intentionally absent."""

    NOT_YET_DUE = "not_yet_due"
    ACTIVE_WORKFLOW = "active_workflow"
    LEGAL_HOLD = "legal_hold"
    ONGOING_LAWFUL_BASIS = "ongoing_lawful_basis"
    EMPLOYEE_RECORD_OBLIGATION = "employee_record_obligation"
    PROCESSOR_ACTION_PENDING = "processor_action_pending"
    BACKUP_RESTORE_REVIEW_PENDING = "backup_restore_review_pending"
    REVIEW_COMPLETE = "review_complete"
