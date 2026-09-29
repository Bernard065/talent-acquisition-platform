"""Provider-neutral contracts for external job-board listing synchronization."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class JobBoardProviderError(RuntimeError):
    """Classified provider failure; exception text must not contain raw payloads."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        normalized_code = code.strip().lower()
        if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,99}", normalized_code) is None:
            normalized_code = "provider_error"
        super().__init__(normalized_code)
        self.code = normalized_code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class PublishJobBoardListingCommand:
    """Immutable public posting data and stable retry identity for an upsert."""

    public_id: UUID
    slug: str
    title: str
    description: str | None
    department: str | None
    location: str | None
    employment_type: str
    expires_at: datetime | None
    external_posting_id: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PublishedJobBoardListing:
    """Safe external identifier returned after an idempotent upsert."""

    external_posting_id: str


@dataclass(frozen=True, slots=True)
class UnpublishJobBoardListingCommand:
    """Minimal data required to idempotently remove one external listing."""

    public_id: UUID
    external_posting_id: str
    idempotency_key: str


class JobBoardProvider(Protocol):
    """Adapter boundary implemented independently for each selected provider.

    Calls must honor cancellation and use stable idempotency keys. Dispatch also
    applies a deadline shorter than the database lease so a slow provider cannot
    outlive its publication-level concurrency reservation.
    """

    provider_key: str

    async def publish(
        self,
        *,
        command: PublishJobBoardListingCommand,
    ) -> PublishedJobBoardListing:
        """Create or update a listing using the supplied idempotency key."""

    async def unpublish(
        self,
        *,
        command: UnpublishJobBoardListingCommand,
    ) -> None:
        """Remove a listing idempotently using the supplied idempotency key."""
