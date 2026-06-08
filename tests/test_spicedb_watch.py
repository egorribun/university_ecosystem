import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.spicedb_watch import (
    _invalidate_for_update,
    _watch_once,
    get_watch_task_age,
    start_permission_watch,
)


def test_invalidate_for_update():
    # Cache format: (user_id, resource_type, resource_id, permission) -> (result, timestamp)
    cache = {
        ("user-1", "document", "doc-123", "read"): (True, time.monotonic()),
        ("user-1", "document", "doc-123", "write"): (False, time.monotonic()),
        ("user-2", "document", "doc-123", "read"): (True, time.monotonic()),
        ("user-1", "folder", "fold-456", "read"): (True, time.monotonic()),
    }

    # Mock relationship update object
    mock_update = MagicMock()
    mock_update.relationship.resource.object_type = "document"
    mock_update.relationship.resource.object_id = "doc-123"
    mock_update.relationship.subject.object.object_id = "user-1"

    _invalidate_for_update(mock_update, cache)

    # Should evict matching entries for user-1 + document + doc-123
    assert ("user-1", "document", "doc-123", "read") not in cache
    assert ("user-1", "document", "doc-123", "write") not in cache
    # Should NOT evict user-2
    assert ("user-2", "document", "doc-123", "read") in cache
    # Should NOT evict other resources for user-1
    assert ("user-1", "folder", "fold-456", "read") in cache

    # Should handle malformed update shapes gracefully
    malformed_update = MagicMock()
    del malformed_update.relationship
    # Should not raise exception
    _invalidate_for_update(malformed_update, cache)


@pytest.mark.anyio
async def test_watch_once_insecure():
    mock_channel = AsyncMock()
    mock_stub = MagicMock()

    # Mock response generator for stub.Watch
    mock_response = MagicMock()
    mock_update = MagicMock()
    mock_update.relationship.resource.object_type = "document"
    mock_update.relationship.resource.object_id = "doc-789"
    mock_update.relationship.subject.object.object_id = "user-abc"
    mock_response.updates = [mock_update]

    async def mock_watch_stream(*args, **kwargs):
        yield mock_response

    mock_stub.Watch = mock_watch_stream

    # Setup cache
    cache = {("user-abc", "document", "doc-789", "read"): (True, time.monotonic())}

    with patch("grpc.aio.insecure_channel", return_value=mock_channel) as mock_insecure:
        with patch("authzed.api.v1.WatchServiceStub", return_value=mock_stub):
            with patch("app.auth.rbac._permission_cache", cache):
                await _watch_once(
                    token="key", host="localhost", port=50051, use_ssl=False
                )

                mock_insecure.assert_called_once_with("localhost:50051")
                assert ("user-abc", "document", "doc-789", "read") not in cache
                mock_channel.close.assert_called_once()


@pytest.mark.anyio
async def test_watch_once_secure():
    mock_channel = AsyncMock()
    mock_stub = MagicMock()

    async def empty_generator(*args, **kwargs):
        if False:
            yield

    mock_stub.Watch = empty_generator

    with patch("grpc.aio.secure_channel", return_value=mock_channel) as mock_secure:
        with patch(
            "grpcutil.bearer_token_credentials", return_value=MagicMock()
        ) as mock_creds:
            with patch("authzed.api.v1.WatchServiceStub", return_value=mock_stub):
                await _watch_once(
                    token="secret-token", host="localhost", port=50051, use_ssl=True
                )

                mock_secure.assert_called_once()
                mock_creds.assert_called_once_with("secret-token")
                mock_channel.close.assert_called_once()


@pytest.mark.anyio
async def test_start_permission_watch_disabled(caplog):
    # If spicedb_endpoint is not set, start_permission_watch returns early
    with patch("app.core.spicedb_watch.settings") as mock_settings:
        mock_settings.spicedb_endpoint = ""
        mock_settings.spicedb_preshared_key = ""

        await start_permission_watch()
        # No loops, returns immediately


@pytest.mark.anyio
async def test_start_permission_watch_loop():
    # Setup config
    with patch("app.core.spicedb_watch.settings") as mock_settings:
        mock_settings.spicedb_endpoint = "localhost:50051"
        mock_settings.spicedb_preshared_key = "secret"

        # Mock cache to clear
        cache = {("user", "doc", "1", "read"): (True, time.monotonic())}

        # _watch_once fails on first call, raises CancelledError on second call
        call_count = 0

        async def mock_watch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("connection error")
            raise asyncio.CancelledError()

        with patch("app.core.spicedb_watch._watch_once", side_effect=mock_watch):
            with patch("app.auth.rbac._permission_cache", cache):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    await start_permission_watch()

                    # On connection error, cache should be cleared
                    assert len(cache) == 0
                    # Reconnect backoff sleep was called
                    mock_sleep.assert_called_once_with(1.0)


def test_get_watch_task_age():
    # Empty cache
    with patch("app.auth.rbac._permission_cache", {}):
        assert get_watch_task_age() is None

    # Cache with entries
    now = time.monotonic()
    cache = {
        ("user1", "resource", "1", "perm"): (True, now - 10.0),
        ("user2", "resource", "2", "perm"): (True, now - 5.0),
    }
    with patch("app.auth.rbac._permission_cache", cache):
        age = get_watch_task_age()
        assert age is not None
        # Age should correspond to oldest timestamp (now - 10.0) -> approx 10 seconds
        assert 9.0 <= age <= 11.0
