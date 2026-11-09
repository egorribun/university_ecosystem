"""Alembic must fail closed when no database URL is configured.

Every command refuses before it opens a database when neither an explicit URL
nor an injected connection is supplied. Development defaults describe metadata,
not permission to migrate or report success without checking anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.migration_settings import MigrationSettings, resolve_migration_url

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Every name that could supply a database, secret, environment selector, CI exemption
# or env file to the child. Windows folds names to upper case, so match case-insensitively.
_INHERITED_AUTHORITY_NAMES = frozenset(
    {
        "database_url",
        "database_url_file",
        "secret_key",
        "secret_key_file",
        "environment",
        "env_file_path",
        "ci",
        "github_actions",
    }
)


def _alembic_environment(**overrides: str) -> dict[str, str]:
    """Return a child environment with no inherited database or secret authority."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.casefold() not in _INHERITED_AUTHORITY_NAMES
    }
    environment["ENV_FILE_PATH"] = ""
    environment.update(overrides)
    return environment


def _run_alembic(
    arguments: list[str], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [sys.executable, "-m", "alembic", *arguments],
        cwd=_PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )


@pytest.mark.parametrize("environment_name", ["development", "testing"])
def test_check_refuses_the_development_skip_without_a_database_url(
    environment_name: str,
) -> None:
    """A verification command must not report success after silently migrating nothing."""

    result = _run_alembic(["check"], _alembic_environment(ENVIRONMENT=environment_name))
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Database URL is not configured for Alembic" in output
    assert "Skipping Alembic migrations" not in output


def test_current_refuses_the_development_skip_without_a_database_url() -> None:
    result = _run_alembic(["current"], _alembic_environment(ENVIRONMENT="development"))
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Database URL is not configured for Alembic" in output
    assert "Skipping Alembic migrations" not in output


def test_offline_sql_refuses_the_development_fallback_without_a_database_url() -> None:
    """Offline SQL for the local SQLite fallback is never a PostgreSQL migration artifact."""

    result = _run_alembic(
        ["upgrade", "head", "--sql"], _alembic_environment(ENVIRONMENT="development")
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Database URL is not configured for Alembic" in output
    assert "CREATE TABLE" not in result.stdout


def test_production_without_a_database_url_fails_closed_for_check() -> None:
    result = _run_alembic(["check"], _alembic_environment(ENVIRONMENT="production"))
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Skipping Alembic migrations" not in output


@pytest.mark.parametrize(
    "environment_name", ["development", "testing", "staging", "production"]
)
@pytest.mark.parametrize(
    "command", [["upgrade", "head"], ["downgrade", "base"], ["check"], ["current"]]
)
def test_commands_without_explicit_target_never_succeed(
    command: list[str], environment_name: str
) -> None:
    result = _run_alembic(command, _alembic_environment(ENVIRONMENT=environment_name))
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "Database URL is not configured for Alembic" in output
    assert "Skipping Alembic migrations" not in output


@pytest.mark.parametrize(
    "source",
    [
        MigrationSettings(None, "missing"),
        MigrationSettings("sqlite:///metadata-only.db", "development-default"),
    ],
)
def test_database_source_without_explicit_authority_refuses(
    source: MigrationSettings,
) -> None:
    """The resolver behind env.py rejects both absent and metadata-only targets."""
    with pytest.raises(
        RuntimeError, match=r"^Database URL is not configured for Alembic$"
    ):
        resolve_migration_url(source, ini_url=None)
