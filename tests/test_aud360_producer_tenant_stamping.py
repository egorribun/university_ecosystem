"""AUD-360: operator-created accounts are owned by the configured MVP tenant."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.db import app as cli_app
from app.core.config import settings

_TENANT = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute.return_value = empty
    return session


def _create_admin(session: AsyncMock, email: str) -> object:
    with (
        patch("app.cli.db.async_session", return_value=session),
        patch(
            "app.cli.db.get_password_hash",
            new_callable=AsyncMock,
            return_value="hashed",
        ),
    ):
        result = CliRunner().invoke(
            cli_app, ["create-admin", "--email", email, "--password", "pw"]
        )
    assert result.exit_code == 0, result.output
    return session.add.call_args.args[0]


def test_operator_created_admin_is_owned_by_the_configured_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT)

    added = _create_admin(_session(), "owner@admin.invalid")

    assert added.tenant_id == _TENANT


def test_operator_created_admin_without_configured_tenant_stays_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mvp_tenant_id", None)

    added = _create_admin(_session(), "solo@admin.invalid")

    assert added.tenant_id is None
