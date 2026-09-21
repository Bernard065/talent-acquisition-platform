"""Strict private API contracts for HRIS handoff operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.hris.enums import HrisHandoffStatus, HrisProvider


class HrisHandoffOperationResponse(BaseModel):
    """
    Safe tenant-admin operational metadata for one HRIS handoff.

    Candidate data, application data, onboarding snapshots, credentials,
    credential references, vault paths, and outbox payloads are excluded.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    provider: HrisProvider
    status: HrisHandoffStatus
    version: int = Field(ge=1)
    attempt_count: int = Field(ge=0)
    last_error_code: str | None
    last_attempt_at: datetime | None
    succeeded_at: datetime | None
    external_employee_reference: str | None
    created_at: datetime
    updated_at: datetime


class HrisHandoffOperationListResponse(BaseModel):
    """Cursor-paginated private HRIS handoff operations."""

    model_config = ConfigDict(extra="forbid")

    items: list[HrisHandoffOperationResponse]
    next_cursor: str | None = None
