"""Container health check for the processor deletion worker."""

import asyncio
import time

from app.core.config import get_settings
from app.db.session import Database


async def main() -> None:
    settings = get_settings()
    heartbeat_path = settings.candidate_processor_deletion_worker_heartbeat_path
    if not heartbeat_path.exists():
        raise RuntimeError("Processor deletion worker heartbeat is missing.")
    if time.time() - heartbeat_path.stat().st_mtime > (
        settings.candidate_processor_deletion_worker_heartbeat_max_age_seconds
    ):
        raise RuntimeError("Processor deletion worker heartbeat is stale.")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for worker health checks.")

    database = Database(str(settings.database_url))
    try:
        await database.ping()
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
