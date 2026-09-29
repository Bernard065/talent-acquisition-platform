"""External job-board publication states and requested operations."""

from enum import StrEnum


class JobBoardPublicationStatus(StrEnum):
    """Synchronization state of one job posting on one external board."""

    PUBLISH_REQUESTED = "publish_requested"
    PUBLISHED = "published"
    UNPUBLISH_REQUESTED = "unpublish_requested"
    UNPUBLISHED = "unpublished"
    FAILED = "failed"


class JobBoardPublicationOperation(StrEnum):
    """Desired remote action carried by the transactional outbox."""

    PUBLISH = "publish"
    UNPUBLISH = "unpublish"


class JobBoardUnpublishReason(StrEnum):
    """Closed set of reasons that may be recorded for a remote unpublish."""

    MANUAL = "manual"
    JOB_POSTING_UNPUBLISHED = "job_posting_unpublished"
    REQUISITION_CLOSED = "requisition_closed"
    REQUISITION_CANCELLED = "requisition_cancelled"
    JOB_POSTING_EXPIRED = "job_posting_expired"
