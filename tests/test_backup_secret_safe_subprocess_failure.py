from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scripts import backup_db


def test_env_database_password_stays_out_of_argv_and_cli_error_output(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "synthetic-subprocess-password-marker"
    database_url = (
        backup_db.make_url("postgresql://backup_user@127.0.0.1/synthetic_source")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(
        backup_db,
        "s3_settings_from_environment",
        lambda: backup_db.S3Settings(
            endpoint_url="https://s3.example.test",
            bucket="synthetic-backups",
            prefix="synthetic",
            region="test-region",
        ),
    )
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )

    calls: list[dict[str, Any]] = []

    def failing_runner(command: list[str], **kwargs: Any) -> Any:
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=2)

    real_dump_database = backup_db.dump_database

    def dump_with_fake_subprocess(url: str, archive_path: Any) -> None:
        real_dump_database(url, archive_path, command_runner=failing_runner)

    monkeypatch.setattr(backup_db, "dump_database", dump_with_fake_subprocess)

    result = backup_db.main(["backup"])
    output = capsys.readouterr()

    assert result == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["command"][0] == "pg_dump"
    assert marker not in " ".join(call["command"])
    assert call["env"]["PGPASSWORD"] == marker
    assert call["stdin"] is backup_db.subprocess.DEVNULL
    assert call["stdout"] is backup_db.subprocess.DEVNULL
    assert call["stderr"] is backup_db.subprocess.DEVNULL
    assert "pg_dump failed with exit code 2" in output.err
    assert marker not in output.out + output.err
