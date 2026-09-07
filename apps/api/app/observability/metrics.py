"""Low-cardinality Prometheus metrics for document scanning operations."""

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.db.models.outbox import OutboxEvent
from app.domains.outbox.enums import OutboxEventStatus
from app.services.document_scan_worker import DocumentScanWorkerResult

DOCUMENT_SCAN_WORKER_EVENTS = Counter(
    "tap_document_scan_worker_events",
    "Outbox scan events handled by outcome.",
    labelnames=("outcome",),
)

DOCUMENT_SCAN_WORKER_POLL_DURATION_SECONDS = Histogram(
    "tap_document_scan_worker_poll_duration_seconds",
    "Duration of one document scan worker polling cycle.",
)

DOCUMENT_SCAN_WORKER_HEARTBEAT_UNIXTIME = Gauge(
    "tap_document_scan_worker_heartbeat_unixtime",
    "Unix timestamp of the most recent document scan worker heartbeat.",
)

OUTBOX_EVENTS = Gauge(
    "tap_outbox_events",
    "Current transactional outbox event count by lifecycle status.",
    labelnames=("status",),
)


def record_document_scan_worker_result(
    result: DocumentScanWorkerResult,
) -> None:
    """Record bounded event outcome counters for one worker polling cycle."""
    if result.processed:
        DOCUMENT_SCAN_WORKER_EVENTS.labels("processed").inc(result.processed)

    if result.retried:
        DOCUMENT_SCAN_WORKER_EVENTS.labels("retried").inc(result.retried)

    if result.dead_lettered:
        DOCUMENT_SCAN_WORKER_EVENTS.labels("dead_lettered").inc(
            result.dead_lettered
        )


async def observe_outbox_backlog(session: AsyncSession) -> None:
    """Refresh bounded queue-depth metrics without tenant-level labels."""
    rows = await session.execute(
        select(
            OutboxEvent.status,
            count(OutboxEvent.id),
        ).group_by(OutboxEvent.status)
    )
    counts = {
        status: count
        for status, count in rows.all()
    }

    for status in OutboxEventStatus:
        OUTBOX_EVENTS.labels(status.value).set(counts.get(status, 0))
