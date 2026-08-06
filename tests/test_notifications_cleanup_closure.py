"""Closure tests for notification retention cleanup branches."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_cleanup_stale_notifications_uses_settings_and_owned_session(monkeypatch):
    db = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db.scalars = AsyncMock(return_value=scalar_result)
    settings = SimpleNamespace(
        notifications_retention_days=30,
        notifications_retention_batch_size=10,
    )
    monkeypatch.setattr("app.services.notifications.cleanup.settings", settings)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=db)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.notifications.cleanup._async_session", session_factory):
        result = await cleanup_stale_notifications(
            now=datetime.now(UTC),
        )

    assert result == (0, 0)
    assert db.commit.await_count == 2


async def test_cleanup_stale_notifications_deletes_delivery_and_notification_batches(
    monkeypatch,
):
    db = AsyncMock()
    delivery_ids = MagicMock()
    delivery_ids.all.return_value = [11]
    no_delivery_ids = MagicMock()
    no_delivery_ids.all.return_value = []
    notification_ids = MagicMock()
    notification_ids.all.return_value = [22]
    no_notification_ids = MagicMock()
    no_notification_ids.all.return_value = []
    db.scalars = AsyncMock(
        side_effect=[
            delivery_ids,
            no_delivery_ids,
            notification_ids,
            no_notification_ids,
        ]
    )
    db.execute = AsyncMock(side_effect=[MagicMock(rowcount=2), MagicMock(rowcount=3)])
    monkeypatch.setattr(
        "app.services.notifications.cleanup.settings",
        SimpleNamespace(
            notifications_retention_days=30,
            notifications_retention_batch_size=1,
        ),
    )

    result = await cleanup_stale_notifications(db=db, now=datetime.now(UTC))

    assert result == (3, 2)
    assert db.execute.await_count == 2
    assert db.commit.await_count == 4


async def test_cleanup_stale_notifications_skips_non_positive_retention():
    db = AsyncMock()

    result = await cleanup_stale_notifications(db=db, retention_days=0)

    assert result == (0, 0)
    db.scalars.assert_not_awaited()
