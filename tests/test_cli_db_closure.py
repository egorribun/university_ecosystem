"""Closure tests for missing-password branches in database CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from typer.testing import CliRunner

from app.cli.db import app
from app.core.config import settings

runner = CliRunner()


def _session(result):
    session = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = UUID(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )
    session.execute.side_effect = [tenant_result, result]
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    session.add = MagicMock()
    return session


def test_create_admin_existing_requires_password():
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock(
        id="user-id", tenant_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    )
    session = _session(result)

    with (
        patch("app.cli.db.async_session", return_value=session),
        patch.object(
            settings, "mvp_tenant_id", UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        ),
    ):
        command = runner.invoke(
            app,
            ["create-admin", "--email", "existing@example.com", "--password", ""],
        )

    assert command.exit_code == 1
    assert "Password required for reset" in command.stdout
    session.commit.assert_not_awaited()


def test_create_admin_new_requires_password():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = _session(result)

    with (
        patch("app.cli.db.async_session", return_value=session),
        patch.object(
            settings, "mvp_tenant_id", UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        ),
    ):
        command = runner.invoke(
            app,
            ["create-admin", "--email", "new@example.com", "--password", ""],
        )

    assert command.exit_code == 1
    assert "Password required for new account" in command.stdout
    session.add.assert_not_called()
