"""Persist liveness markers for worker services."""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.worker_heartbeat import WorkerHeartbeat

CALENDAR_SYNC_WORKER_NAME = "calendar_sync"


async def record_worker_heartbeat(
    session: AsyncSession,
    *,
    worker_name: str,
) -> None:
    """Upsert a worker's most recent successful heartbeat timestamp."""
    now = datetime.now(UTC)
    statement = insert(WorkerHeartbeat).values(
        worker_name=worker_name,
        last_heartbeat_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_name],
            set_={"last_heartbeat_at": now},
        )
    )
