"""Long-running outbox worker that removes candidate document objects."""

import asyncio
import os
import socket
import time
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.object_storage.s3 import S3ObjectStorage
from app.services.candidate_document_erasure_worker import (
    process_candidate_document_erasure_events,
)
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    if configured_worker_id is not None:
        return configured_worker_id
    return f"candidate-privacy:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def main() -> None:
    """Poll the outbox and safely remove bounded batches of candidate files."""
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for the candidate privacy worker.")

    database = Database(str(settings.database_url))
    storage: S3ObjectStorage | None = None
    worker_id = _worker_id(settings.candidate_privacy_worker_id)
    policy = OutboxWorkerPolicy(batch_size=settings.candidate_privacy_worker_batch_size)
    heartbeat_path = settings.candidate_privacy_worker_heartbeat_path

    try:
        storage = S3ObjectStorage.from_settings(settings)
        logger.info("candidate_privacy_worker_started", worker_id=worker_id)
        while True:
            cycle_started = time.monotonic()
            try:
                async with database.session_factory() as session:
                    result = await process_candidate_document_erasure_events(
                        session,
                        worker_id=worker_id,
                        storage=storage,
                        policy=policy,
                    )
                _record_heartbeat(heartbeat_path)

                if result.claimed:
                    logger.info(
                        "candidate_privacy_worker_batch_complete",
                        worker_id=worker_id,
                        claimed=result.claimed,
                        processed=result.processed,
                        retried=result.retried,
                        dead_lettered=result.dead_lettered,
                        duration_seconds=round(time.monotonic() - cycle_started, 3),
                    )
                else:
                    await asyncio.sleep(
                        settings.candidate_privacy_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "candidate_privacy_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.candidate_privacy_worker_poll_interval_seconds
                )
    finally:
        if storage is not None:
            storage.close()
        await database.dispose()
        logger.info("candidate_privacy_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
