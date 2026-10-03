from __future__ import annotations

import asyncio
import subprocess

import pytest

from scripts.quality.migrate_passwords_image_gate import (
    GateFailure,
    _assert_cli_result,
    _docker_command,
    _drop_reader_role_if_present,
    _finalize_gate,
    _validated_database_url,
    _validated_image_id,
)

_LOCAL_DATABASE_URL = "postgresql+asyncpg://test@localhost:5433/test_migration"
_IMAGE_ID = f"sha256:{'a' * 64}"


class _CleanupResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _CleanupConnection:
    def __init__(self, *, role_exists: bool) -> None:
        self.role_exists = role_exists
        self.statements: list[str] = []

    async def execute(self, statement: object, *_: object) -> _CleanupResult:
        query = str(statement)
        self.statements.append(query)
        if query.startswith("SELECT 1 FROM pg_roles"):
            return _CleanupResult(1 if self.role_exists else None)
        return _CleanupResult(None)


@pytest.mark.parametrize(
    ("role_exists", "expected_drop_count"), [(False, 0), (True, 2)]
)
def test_cleanup_drops_reader_only_if_role_survived_transaction(
    role_exists: bool, expected_drop_count: int
) -> None:
    connection = _CleanupConnection(role_exists=role_exists)

    asyncio.run(_drop_reader_role_if_present(connection))

    assert connection.statements[0].startswith("SELECT 1 FROM pg_roles")
    assert sum(
        statement.startswith("DROP ") for statement in connection.statements
    ) == (expected_drop_count)


def test_finalize_preserves_gate_error_and_attempts_dispose() -> None:
    primary_error = ValueError("gate failed")
    events: list[str] = []

    async def cleanup() -> None:
        events.append("cleanup")
        raise RuntimeError("cleanup failed")

    async def dispose() -> None:
        events.append("dispose")
        raise OSError("disposal failed")

    asyncio.run(_finalize_gate(cleanup, dispose, primary_error))

    assert events == ["cleanup", "dispose"]
    assert any("RuntimeError" in note for note in primary_error.__notes__)
    assert any("OSError" in note for note in primary_error.__notes__)


def test_finalize_surfaces_cleanup_error_when_gate_succeeded() -> None:
    async def cleanup() -> None:
        raise RuntimeError("cleanup failed")

    async def dispose() -> None:
        return None

    with pytest.raises(RuntimeError, match="cleanup failed"):
        asyncio.run(_finalize_gate(cleanup, dispose, None))


def test_finalize_surfaces_disposal_error_when_gate_succeeded() -> None:
    async def cleanup() -> None:
        return None

    async def dispose() -> None:
        raise OSError("disposal failed")

    with pytest.raises(OSError, match="disposal failed"):
        asyncio.run(_finalize_gate(cleanup, dispose, None))


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
