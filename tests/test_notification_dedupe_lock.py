"""Dialect-specific notification lock behavior in SQLite coverage runs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.notifications.dedupe import lock_notification_dedupe


@pytest.mark.asyncio
async def test_notification_lock_uses_bound_postgresql_key() -> None:
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.execute = AsyncMock()

    await lock_notification_dedupe(db, "system.release:9.0.0")

    db.execute.assert_awaited_once()
    statement, parameters = db.execute.await_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert parameters == {"dedupe_key": "system.release:9.0.0"}


@pytest.mark.asyncio
async def test_notification_lock_skips_sqlite() -> None:
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    db.execute = AsyncMock()

    await lock_notification_dedupe(db, "system.release:9.0.0")

    db.execute.assert_not_awaited()
