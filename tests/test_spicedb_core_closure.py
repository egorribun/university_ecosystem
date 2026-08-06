"""Branch closure tests for the SpiceDB client provider."""

from unittest.mock import MagicMock, patch

import pytest

import app.core.spicedb as spicedb


def test_channel_lock_double_check_uses_lock_created_by_guard(monkeypatch):
    created = MagicMock()

    class Guard:
        def __enter__(self):
            spicedb._global_channel_lock = created
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(spicedb, "_global_channel_lock", None)
    monkeypatch.setattr(spicedb, "_global_channel_alloc_lock", Guard())

    assert spicedb._get_channel_lock() is created


@pytest.mark.asyncio
async def test_async_channel_double_check_yields_channel_created_while_waiting(
    monkeypatch,
):
    channel = MagicMock()

    class AsyncGuard:
        async def __aenter__(self):
            spicedb._global_channel = channel
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(spicedb, "_global_channel", None)
    monkeypatch.setattr(spicedb, "_get_channel_lock", lambda: AsyncGuard())

    with patch("grpc.aio.secure_channel") as secure_channel:
        result = [item async for item in spicedb.get_async_spicedb_channel()]

    assert result == [channel]
    secure_channel.assert_not_called()


@pytest.mark.asyncio
async def test_close_global_channel_is_noop_when_channel_is_absent(monkeypatch):
    monkeypatch.setattr(spicedb, "_global_channel", None)

    await spicedb.close_global_spicedb_channel()
