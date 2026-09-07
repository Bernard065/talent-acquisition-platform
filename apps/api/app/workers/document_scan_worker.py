"""Long-running worker for asynchronous candidate document malware scans."""

import asyncio
import os
import socket
import time
from pathlib import Path

import structlog
from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.malware_scanning.clamav import (
    ClamAvConfig,
    ClamAvMalwareScanner,
)
from app.infrastructure.object_storage.s3 import S3ObjectStorage
from app.observability.metrics import (
    DOCUMENT_SCAN_WORKER_HEARTBEAT_UNIXTIME,
    DOCUMENT_SCAN_WORKER_POLL_DURATION_SECONDS,
    observe_outbox_backlog,
    record_document_scan_worker_result,
)
from app.services.document_scan_worker import (
    process_candidate_document_scan_events,
)
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Use an explicit ID when configured, otherwise identify this process."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"document-scanner:{socket.gethostname()}:{os.getpid()}"


def _record_heartbeat(path: Path) -> None:
    """Persist a liveness marker visible to the container health-check process."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    DOCUMENT_SCAN_WORKER_HEARTBEAT_UNIXTIME.set(time.time())


async def main() -> None:
    """Poll the transactional outbox and process bounded scan batches."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for the scanner worker.")

    database = Database(str(settings.database_url))
    storage = S3ObjectStorage.from_settings(settings)
    scanner = ClamAvMalwareScanner(
        storage=storage,
        config=ClamAvConfig(
            host=settings.clamav_host,
            port=settings.clamav_port,
            timeout_seconds=settings.clamav_timeout_seconds,
            max_stream_bytes=settings.clamav_max_stream_bytes,
        ),
    )
    worker_id = _worker_id(settings.scan_worker_id)
    policy = OutboxWorkerPolicy(batch_size=settings.scan_worker_batch_size)
    heartbeat_path = settings.scan_worker_heartbeat_path
    metrics_server, metrics_thread = start_http_server(
        settings.scan_worker_metrics_port
    )

    logger.info("document_scan_worker_started", worker_id=worker_id)

    try:
        while True:
            cycle_started = time.monotonic()

            try:
                async with database.session_factory() as session:
                    result = await process_candidate_document_scan_events(
                        session,
                        worker_id=worker_id,
                        scanner=scanner,
                        policy=policy,
                    )
                    await observe_outbox_backlog(session)

                record_document_scan_worker_result(result)
                _record_heartbeat(heartbeat_path)

                if result.claimed:
                    logger.info(
                        "document_scan_worker_batch_complete",
                        worker_id=worker_id,
                        claimed=result.claimed,
                        processed=result.processed,
                        retried=result.retried,
                        dead_lettered=result.dead_lettered,
                    )
                else:
                    await asyncio.sleep(
                        settings.scan_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "document_scan_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.scan_worker_poll_interval_seconds
                )
            finally:
                DOCUMENT_SCAN_WORKER_POLL_DURATION_SECONDS.observe(
                    time.monotonic() - cycle_started
                )
    finally:
        metrics_server.shutdown()
        metrics_server.server_close()
        metrics_thread.join(timeout=5)
        await database.dispose()
        logger.info("document_scan_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
