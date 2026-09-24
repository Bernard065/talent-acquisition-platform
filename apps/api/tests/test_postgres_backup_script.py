"""Safety tests for the local PostgreSQL backup and restore utility."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "postgres_backup.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("tap_postgres_backup", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
backup_script = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(backup_script)


def test_smoke_database_name_must_match_generated_format() -> None:
    valid_name = "tap_restore_smoke_" + "a" * 32

    assert backup_script.validate_smoke_database_name(valid_name) == valid_name
    for unsafe_name in ("tap", "tap_restore_smoke_other", "tap_restore_smoke_" + "a" * 31):
        with pytest.raises(backup_script.BackupCommandError):
            backup_script.validate_smoke_database_name(unsafe_name)


def test_local_backup_tool_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(backup_script.BackupCommandError, match="local.*test"):
        backup_script._ensure_local_environment()


def test_backup_never_overwrites_an_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    destination = tmp_path / "existing.dump"
    destination.write_bytes(b"keep this backup")

    with pytest.raises(FileExistsError):
        backup_script.create_backup(destination)

    assert destination.read_bytes() == b"keep this backup"


def test_backup_preserves_custom_format_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    destination = tmp_path / "backup.dump"
    archive_bytes = b"\x00PGDMP\xffbinary archive"

    def write_fake_archive(arguments: list[str], *, stdout: object) -> None:
        assert "pg_dump" in " ".join(arguments)
        stdout.write(archive_bytes)  # type: ignore[attr-defined]

    monkeypatch.setattr(backup_script, "_run", write_fake_archive)
    backup_script.create_backup(destination)

    assert destination.read_bytes() == archive_bytes
