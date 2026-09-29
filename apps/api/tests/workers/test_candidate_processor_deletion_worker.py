"""Worker startup safety tests for processor deletion dispatch."""

from types import SimpleNamespace

import pytest

from app.workers import candidate_processor_deletion_worker


@pytest.mark.asyncio
async def test_worker_is_disabled_by_default_before_runtime_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never create provider clients or run erasure while the safety gate is off."""
    monkeypatch.setattr(
        candidate_processor_deletion_worker,
        "get_settings",
        lambda: SimpleNamespace(
            log_level="INFO",
            candidate_processor_deletion_worker_enabled=False,
        ),
    )
    monkeypatch.setattr(
        candidate_processor_deletion_worker,
        "configure_logging",
        lambda _: None,
    )

    async def forbidden_runtime(_: object) -> object:
        pytest.fail("Provider runtime must not initialize while dispatch is disabled")

    monkeypatch.setattr(
        candidate_processor_deletion_worker,
        "_build_runtime",
        forbidden_runtime,
    )

    with pytest.raises(RuntimeError, match="dispatch is disabled"):
        await candidate_processor_deletion_worker.main()
