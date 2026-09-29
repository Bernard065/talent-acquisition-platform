"""Deterministic local-only job-board provider for development smoke testing."""

from dataclasses import dataclass

from app.services.job_board_provider import (
    JobBoardProvider,
    PublishedJobBoardListing,
    PublishJobBoardListingCommand,
    UnpublishJobBoardListingCommand,
)


@dataclass(frozen=True, slots=True)
class LocalJobBoardProvider(JobBoardProvider):
    """Simulate publication without network access or external side effects."""

    provider_key: str = "local"

    async def publish(
        self,
        *,
        command: PublishJobBoardListingCommand,
    ) -> PublishedJobBoardListing:
        """Return a stable local reference suitable for retry testing."""
        return PublishedJobBoardListing(
            external_posting_id=f"local-{command.public_id}"
        )

    async def unpublish(
        self,
        *,
        command: UnpublishJobBoardListingCommand,
    ) -> None:
        """Acknowledge removal without performing any external action."""
        _ = command
