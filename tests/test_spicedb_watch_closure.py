"""Closure tests for watch clean reconnect and metrics guard paths."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.spicedb_watch import _invalidate_for_update, start_permission_watch


def _update():
    return SimpleNamespace(
        relationship=SimpleNamespace(
            resource=SimpleNamespace(object_type="document", object_id="doc-1"),
            subject=SimpleNamespace(object=SimpleNamespace(object_id="user-1")),
        )
    )


@pytest.mark.asyncio
async def test_invalidate_for_update_swallows_metrics_failure():
    cache = {}
    redis_cache = MagicMock()
    redis_cache.invalidate = AsyncMock()
    ws_client = MagicMock()
    ws_client.publish_control_event = AsyncMock()

    with (
        patch("app.deps.cache.get_cache", return_value=redis_cache),
        patch("app.services.ws_hub_client._get_client", return_value=ws_client),
        patch(
            "app.core.metrics.record_spicedb_watch_event",
            side_effect=RuntimeError("metrics unavailable"),
        ),
    ):
        await _invalidate_for_update(_update(), cache)

    redis_cache.invalidate.assert_awaited_once()
    ws_client.publish_control_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_permission_watch_resets_backoff_after_clean_stream_end():
    with (
        patch("app.core.spicedb_watch.settings") as settings,
        patch("app.auth.rbac._permission_cache", {}),
        patch(
            "app.core.spicedb_watch._watch_once",
            new=AsyncMock(side_effect=[None, asyncio.CancelledError()]),
        ) as watch_once,
        patch("app.core.spicedb_watch.asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        settings.spicedb_endpoint = "localhost:50051"
        settings.spicedb_preshared_key = "secret"

        await start_permission_watch()

    assert watch_once.await_count == 2
    sleep.assert_awaited_once_with(1.0)
