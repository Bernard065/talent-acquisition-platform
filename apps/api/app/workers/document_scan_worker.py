"""Long-running worker for asynchronous candidate document malware scans."""

import asyncio
import os
import socket

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.malware_scanning.clamav import (
    ClamAvConfig,
    ClamAvMalwareScanner,
)
from app.infrastructure.object_storage.s3 import S3ObjectStorage
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

    logger.info("document_scan_worker_started", worker_id=worker_id)

    try:
        while True:
            async with database.session_factory() as session:
                result = await process_candidate_document_scan_events(
                    session,
                    worker_id=worker_id,
                    scanner=scanner,
                    policy=policy,
                )

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
                await asyncio.sleep(settings.scan_worker_poll_interval_seconds)
    finally:
        await database.dispose()
        logger.info("document_scan_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
