from __future__ import annotations

import subprocess

import pytest

from scripts.quality.migrate_passwords_image_gate import (
    GateFailure,
    _assert_cli_result,
    _docker_command,
    _validated_database_url,
    _validated_image_id,
)

_LOCAL_DATABASE_URL = "postgresql+asyncpg://test@localhost:5433/test_migration"
_IMAGE_ID = f"sha256:{'a' * 64}"


def test_database_url_accepts_only_the_passwordless_disposable_service() -> None:
    url = _validated_database_url(_LOCAL_DATABASE_URL)
    assert url.database == "test_migration"
    assert url.password is None

    with pytest.raises(GateFailure, match="outside the disposable CI service"):
        _validated_database_url(
            "postgresql+asyncpg://test@db.example.invalid:5433/test_migration"
        )

    with pytest.raises(GateFailure, match="outside the disposable CI service"):
        _validated_database_url("postgresql+asyncpg://test@localhost:5433/production")

    credentialed_url = "postgresql+asyncpg://test:@localhost:5433/test_migration"
    with pytest.raises(GateFailure, match="outside the disposable CI service"):
        _validated_database_url(credentialed_url)


def test_image_id_requires_full_sha256_and_command_uses_that_id() -> None:
    assert _validated_image_id(_IMAGE_ID) == _IMAGE_ID

    with pytest.raises(GateFailure, match="full SHA-256 image ID"):
        _validated_image_id("local/backend:ci")

    command = _docker_command(_IMAGE_ID)
    assert command[command.index("--entrypoint") + 1] == "/opt/venv/bin/python"
    assert command[command.index("--network") + 1] == "host"
    assert command.index(_IMAGE_ID) > command.index("--entrypoint")
    assert command[-4:] == ["-m", "app.cli", "migrate-passwords", "assert-none"]


@pytest.mark.parametrize(
    ("exit_code", "stdout"),
    [
        (0, "No active legacy bcrypt accounts found."),
        (1, "Legacy bcrypt accounts remain: 1"),
    ],
)
def test_cli_result_accepts_only_the_expected_clean_or_remaining_state(
    exit_code: int, stdout: str
) -> None:
    result = subprocess.CompletedProcess(
        args=["docker"], returncode=exit_code, stdout=f"{stdout}\n", stderr=""
    )
    _assert_cli_result(result, exit_code=exit_code, stdout=stdout)


def test_cli_result_allows_safe_startup_output_before_final_status() -> None:
    result = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="masked startup message\nNo active legacy bcrypt accounts found.\n",
        stderr="",
    )
    _assert_cli_result(
        result, exit_code=0, stdout="No active legacy bcrypt accounts found."
    )


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr"),
    [
        (0, "Legacy bcrypt accounts remain: 1", ""),
        (1, "No active legacy bcrypt accounts found.", ""),
        (1, "Legacy bcrypt accounts remain: 1", "connection error"),
    ],
)
def test_cli_result_fails_closed_on_status_or_connection_diagnostics(
    returncode: int, stdout: str, stderr: str
) -> None:
    result = subprocess.CompletedProcess(
        args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr
    )
    with pytest.raises(GateFailure, match="did not match the expected state"):
        _assert_cli_result(
            result, exit_code=1, stdout="Legacy bcrypt accounts remain: 1"
        )
