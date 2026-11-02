"""Alembic must fail closed when no database URL is configured.

The development skip is a local convenience for ``upgrade`` only. Every other command,
including ``check`` (a verification that must never exit 0 without verifying anything),
refuses before it opens a database. These probes need no database: each refusal happens
before any connection is attempted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

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
    assert "Refusing to skip Alembic migrations" in output
    assert "Skipping Alembic migrations" not in output


def test_current_refuses_the_development_skip_without_a_database_url() -> None:
    result = _run_alembic(["current"], _alembic_environment(ENVIRONMENT="development"))
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Refusing to skip Alembic migrations" in output
    assert "Skipping Alembic migrations" not in output


def test_offline_sql_refuses_the_development_fallback_without_a_database_url() -> None:
    """Offline SQL for the local SQLite fallback is never a PostgreSQL migration artifact."""

    result = _run_alembic(
        ["upgrade", "head", "--sql"], _alembic_environment(ENVIRONMENT="development")
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Refusing to render Alembic SQL" in output
    assert "CREATE TABLE" not in result.stdout


def test_production_without_a_database_url_fails_closed_for_check() -> None:
    result = _run_alembic(["check"], _alembic_environment(ENVIRONMENT="production"))
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Skipping Alembic migrations" not in output
