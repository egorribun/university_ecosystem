"""Closure test for the default notification cleanup batch size."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.notifications.cleanup import cleanup_stale_notifications


async def test_cleanup_stale_notifications_uses_default_batch_size(monkeypatch):
    db = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db.scalars = AsyncMock(return_value=scalar_result)
    settings = SimpleNamespace(
        notifications_retention_days=30,
        notifications_retention_batch_size=0,
    )
    monkeypatch.setattr("app.services.notifications.cleanup.settings", settings)

    result = await cleanup_stale_notifications(
        db=db,
        retention_days=30,
        now=datetime.now(UTC),
    )

    assert result == (0, 0)
    assert db.scalars.await_count == 2
