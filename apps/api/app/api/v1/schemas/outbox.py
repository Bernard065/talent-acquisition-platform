"""API schemas for tenant-scoped outbox operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeadLetterEventResponse(BaseModel):
    """
    Safe operational metadata for a dead-lettered event.

    Deliberately excludes tenant_id, payload, storage keys, candidate data,
    scanner signatures, and worker lease details.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    attempts: int = Field(ge=0)
    last_error: str | None
    created_at: datetime
    dead_lettered_at: datetime


class DeadLetterEventListResponse(BaseModel):
    """Cursor-paginated dead-letter event collection."""

    model_config = ConfigDict(extra="forbid")

    items: list[DeadLetterEventResponse]
    next_cursor: str | None = None
