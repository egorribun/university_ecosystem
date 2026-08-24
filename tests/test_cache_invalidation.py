from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cache_invalidation import (
    CacheInvalidator,
    CacheTag,
    get_tags_for_key,
    invalidate_by_tag,
    invalidate_event_cache,
    invalidate_groups_cache,
    invalidate_news_cache,
    invalidate_schedule_cache,
    invalidate_user_cache,
    invalidates_cache,
    register_key_with_tags,
)


def test_get_tags_for_key():
    assert get_tags_for_key("schedule:group:1") == [CacheTag.SCHEDULE]
    assert get_tags_for_key("user:profile:1") == [CacheTag.USER]
    assert get_tags_for_key("unknown:key") == []


@pytest.mark.asyncio
async def test_register_key_with_tags(monkeypatch):
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    async def mock_get_client():
        return mock_redis

    monkeypatch.setattr("app.deps.cache.get_cache_client", mock_get_client)

    await register_key_with_tags("schedule:group:1", 3600)

    mock_pipe.sadd.assert_called_once_with(
        f"{CacheTag.SCHEDULE}:keys", "schedule:group:1"
    )
    mock_pipe.expire.assert_called_once_with(f"{CacheTag.SCHEDULE}:keys", 3600)
    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_register_key_with_tags_no_tags():
    # Should just return
    await register_key_with_tags("unknown:key")


@pytest.mark.asyncio
async def test_invalidate_by_tag(monkeypatch):
    mock_redis = MagicMock()
    mock_redis.smembers = AsyncMock(
        return_value={b"schedule:group:1", b"schedule:group:2"}
    )
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    async def mock_get_client():
        return mock_redis

    monkeypatch.setattr("app.deps.cache.get_cache_client", mock_get_client)

    count = await invalidate_by_tag(CacheTag.SCHEDULE)
    assert count == 2
    assert mock_pipe.delete.call_count == 3  # 2 keys + 1 tag index


@pytest.mark.asyncio
async def test_invalidate_by_tag_no_keys(monkeypatch):
    mock_redis = MagicMock()
    mock_redis.smembers = AsyncMock(return_value=set())

    async def mock_get_client():
        return mock_redis

    monkeypatch.setattr("app.deps.cache.get_cache_client", mock_get_client)

    count = await invalidate_by_tag(CacheTag.SCHEDULE)
    assert count == 0


@pytest.mark.asyncio
async def test_invalidate_cache_functions(monkeypatch):
    mock_cache = AsyncMock()
    monkeypatch.setattr("app.services.cache_invalidation.get_cache", lambda: mock_cache)

    await invalidate_schedule_cache(1)
    mock_cache.invalidate.assert_called_with("schedule:group:1")

    await invalidate_user_cache(2)
    mock_cache.invalidate.assert_called_with("user:profile:2")

    await invalidate_event_cache(3)
    mock_cache.invalidate.assert_called_with("event:3", "event:list")

    await invalidate_news_cache(4)
    mock_cache.invalidate.assert_called_with("news:4", "news:list")

    await invalidate_groups_cache()
    mock_cache.invalidate.assert_called_with("groups:list")


@pytest.mark.asyncio
async def test_cache_invalidator_context(monkeypatch):
    mock_cache = AsyncMock()
    monkeypatch.setattr("app.services.cache_invalidation.get_cache", lambda: mock_cache)

    async with CacheInvalidator() as inv:
        inv.schedule(1)
        inv.user(2)
        inv.event(3)
        inv.news(4)

    assert mock_cache.invalidate.call_count == 1
    call_args = mock_cache.invalidate.call_args[0]
    assert set(call_args) == {
        "schedule:group:1",
        "user:profile:2",
        "event:3",
        "event:list",
        "news:4",
        "news:list",
    }


@pytest.mark.asyncio
async def test_cache_invalidator_empty():
    async with CacheInvalidator() as inv:
        pass
    assert len(inv._keys) == 0


@pytest.mark.asyncio
async def test_invalidates_cache_decorator(monkeypatch):
    mock_invalidate = AsyncMock()
    monkeypatch.setattr(
        "app.services.cache_invalidation.invalidate_by_tag", mock_invalidate
    )

    @invalidates_cache(CacheTag.EVENT)
    async def do_work():
        return "done"

    res = await do_work()
    assert res == "done"
    mock_invalidate.assert_called_once_with(CacheTag.EVENT)


@pytest.mark.asyncio
async def test_invalidates_cache_decorator_exception(monkeypatch):
    mock_invalidate = AsyncMock()
    monkeypatch.setattr(
        "app.services.cache_invalidation.invalidate_by_tag", mock_invalidate
    )

    @invalidates_cache(CacheTag.EVENT)
    async def do_work():
        raise ValueError("error")

    with pytest.raises(ValueError):
        await do_work()
    mock_invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_register_key_with_tags_connection_error(monkeypatch):
    async def mock_get_client():
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = ConnectionError("Connection refused")
        return mock_redis

    monkeypatch.setattr("app.deps.cache.get_cache_client", mock_get_client)

    # Should handle ConnectionError gracefully
    await register_key_with_tags("schedule:group:1", 3600)


@pytest.mark.asyncio
async def test_invalidate_by_tag_connection_error(monkeypatch):
    async def mock_get_client():
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(side_effect=TimeoutError("Timeout"))
        return mock_redis

    monkeypatch.setattr("app.deps.cache.get_cache_client", mock_get_client)

    # Should handle TimeoutError gracefully and return 0
    res = await invalidate_by_tag(CacheTag.SCHEDULE)
    assert res == 0
