"""Strict private API contracts for tenant-managed HRIS connections."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.domains.hris.enums import HrisConnectionStatus, HrisProvider

CredentialName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    ),
]


class CreateHrisConnectionRequest(BaseModel):
    """Create one tenant-owned HRIS connection using external vault storage."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    provider: HrisProvider
    credentials: dict[CredentialName, SecretStr] = Field(
        min_length=1,
        max_length=32,
    )


class ExpectedHrisConnectionVersionRequest(BaseModel):
    """Optimistic concurrency input for an HRIS lifecycle mutation."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class HrisConnectionResponse(BaseModel):
    """
    Safe HRIS connection metadata.

    Credential values, credential references, creator identity, and deletion
    actor identity are intentionally excluded.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    provider: HrisProvider
    status: HrisConnectionStatus
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class HrisConnectionListResponse(BaseModel):
    """Bounded collection of safe tenant-owned HRIS connection metadata."""

    model_config = ConfigDict(extra="forbid")

    items: list[HrisConnectionResponse]


class HrisConnectionDeletedResponse(BaseModel):
    """Logical-deletion acknowledgement without returning sensitive metadata."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str = "deleted"
