"""Container health check for the job-posting expiry worker."""

import asyncio
import time

from app.core.config import get_settings
from app.db.session import Database


async def main() -> None:
    """Fail unless the worker heartbeat and PostgreSQL are healthy."""
    settings = get_settings()
    heartbeat_path = settings.job_posting_expiry_worker_heartbeat_path

    if not heartbeat_path.exists():
        raise RuntimeError(
            "Job posting expiry worker heartbeat file does not exist."
        )

    heartbeat_age = time.time() - heartbeat_path.stat().st_mtime
    if (
        heartbeat_age
        > settings.job_posting_expiry_worker_heartbeat_max_age_seconds
    ):
        raise RuntimeError("Job posting expiry worker heartbeat is stale.")

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for job posting expiry worker health checks."
        )

    database = Database(str(settings.database_url))
    try:
        await database.ping()
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
