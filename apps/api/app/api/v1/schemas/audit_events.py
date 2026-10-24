"""Response contracts for the workspace audit log."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    """Privacy-conscious summary of one tenant audit event."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    actor_display_name: str | None
    actor_subject: str | None
    action: str
    entity_type: str
    entity_id: str
    request_id: str
    occurred_at: datetime


class AuditEventListResponse(BaseModel):
    """One bounded page of tenant audit history."""

    model_config = ConfigDict(extra="forbid")

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int
