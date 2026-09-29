"""Container health check for the job-board dispatch worker."""

import asyncio
import time

from app.core.config import get_settings
from app.db.session import Database


async def main() -> None:
    """Require a fresh heartbeat and a healthy PostgreSQL connection."""
    settings = get_settings()
    path = settings.job_board_dispatch_worker_heartbeat_path
    if not path.exists():
        raise RuntimeError("Job-board dispatch worker heartbeat is missing.")
    if (
        time.time() - path.stat().st_mtime
        > settings.job_board_dispatch_worker_heartbeat_max_age_seconds
    ):
        raise RuntimeError("Job-board dispatch worker heartbeat is stale.")
    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for job-board worker health checks."
        )

    database = Database(str(settings.database_url))
    try:
        await database.ping()
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
