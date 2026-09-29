"""Tests for the deterministic local job-board adapter."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.infrastructure.job_boards.local_provider import LocalJobBoardProvider
from app.services.job_board_provider import (
    PublishJobBoardListingCommand,
    UnpublishJobBoardListingCommand,
)


@pytest.mark.asyncio
async def test_local_publish_is_deterministic_and_unpublish_is_safe_noop() -> None:
    provider = LocalJobBoardProvider()
    public_id = uuid4()
    command = PublishJobBoardListingCommand(
        public_id=public_id,
        slug="software-engineer",
        title="Software Engineer",
        description="Public description",
        department="Engineering",
        location="Nairobi",
        employment_type="full_time",
        expires_at=datetime(2026, 12, 31, tzinfo=UTC),
        external_posting_id=None,
        idempotency_key="event-id",
    )

    first = await provider.publish(command=command)
    replay = await provider.publish(command=command)
    await provider.unpublish(
        command=UnpublishJobBoardListingCommand(
            public_id=public_id,
            external_posting_id=first.external_posting_id,
            idempotency_key="unpublish-event-id",
        )
    )

    assert first == replay
    assert first.external_posting_id == f"local-{public_id}"
