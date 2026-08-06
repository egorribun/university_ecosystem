"""Focused CLI branch coverage for legacy password migration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli import migrate_passwords
from app.models import User

runner = CliRunner()


@pytest.mark.asyncio
async def test_force_reset_batch_returns_zero_for_argon_only_batch():
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    user = MagicMock(spec=User)
    user.hashed_password = "argon2id$v=19$m=65536"
    result.scalars.return_value.all.return_value = [user]
    session.execute.return_value = result

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._force_reset_batch(10) == (0, 0)


def test_report_lists_count_beyond_sample_limit():
    entries = [{"id": "1", "email": "one@example.com"}]

    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=3)
        ),
        patch.object(
            migrate_passwords,
            "_report_bcrypt_users",
            new=AsyncMock(return_value=entries),
        ),
    ):
        result = runner.invoke(migrate_passwords.app, ["report", "--limit", "1"])

    assert result.exit_code == 0
    assert "and 2 more" in result.stdout


def test_force_reset_uses_confirmation_prompt():
    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=1)
        ),
        patch.object(
            migrate_passwords,
            "_force_reset_batch",
            new=AsyncMock(return_value=(1, 0)),
        ),
        patch.object(migrate_passwords.typer, "confirm", return_value=True) as confirm,
    ):
        result = runner.invoke(migrate_passwords.app, ["force-reset"])

    assert result.exit_code == 0
    confirm.assert_called_once()


def test_force_reset_stops_when_batch_processes_nothing():
    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=1)
        ),
        patch.object(
            migrate_passwords,
            "_force_reset_batch",
            new=AsyncMock(return_value=(0, 1)),
        ),
    ):
        result = runner.invoke(migrate_passwords.app, ["force-reset", "--yes"])

    assert result.exit_code == 0
    assert "Done. 0 account(s)" in result.stdout


def test_force_reset_repeats_when_accounts_remain():
    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=1)
        ),
        patch.object(
            migrate_passwords,
            "_force_reset_batch",
            new=AsyncMock(side_effect=[(1, 1), (1, 0)]),
        ) as batch,
    ):
        result = runner.invoke(migrate_passwords.app, ["force-reset", "--yes"])

    assert result.exit_code == 0
    assert batch.await_count == 2
