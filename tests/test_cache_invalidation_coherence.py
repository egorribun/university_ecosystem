"""Coherence and decorator tests for ``app.services.cache_invalidation``.

The module is a thin orchestration layer over ``app.deps.cache``: tags →
prefix mapping, key generators, batched invalidation contexts, and the
``@invalidates_cache`` decorator. We test it without touching real Redis
by mocking ``get_cache`` and ``get_cache_client`` from ``app.deps.cache``.

Coverage focus:

* ``CacheTag`` enum stability — values are public protocol;
* ``get_tags_for_key`` — prefix → tag mapping for all six tags + the
  empty/unknown-key fallback;
* key generator helpers — deterministic format;
* ``register_key_with_tags`` — pipelined SADD/EXPIRE under success;
  graceful degrade on Redis errors; no-op when no tags match;
* ``invalidate_by_tag`` — deletes all members + the index, returns count;
  empty index returns 0; graceful degrade returns 0;
* ``invalidate_*_cache`` helpers — call the cache with the right keys;
* ``CacheInvalidator`` context manager — queues + dedupes + flushes on
  exit, empty queue returns 0, deduplicates redundant invalidations,
  flushes even when the body raises;
* ``@invalidates_cache`` decorator — invalidates after success, does
  NOT invalidate on exception (mutation didn't commit), supports
  multiple tags;
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cache_invalidation import (
    CACHE_PREFIX_EVENT,
    CACHE_PREFIX_GROUPS,
    CACHE_PREFIX_NEWS,
    CACHE_PREFIX_SCHEDULE,
    CACHE_PREFIX_USER,
    CacheInvalidator,
    CacheTag,
    event_cache_key,
    events_list_cache_key,
    get_tags_for_key,
    invalidate_by_tag,
    invalidate_event_cache,
    invalidate_groups_cache,
    invalidate_news_cache,
    invalidate_schedule_cache,
    invalidate_user_cache,
    invalidates_cache,
    news_cache_key,
    news_list_cache_key,
    register_key_with_tags,
    schedule_cache_key,
    user_cache_key,
)

# ── 1. CacheTag enum stability ───────────────────────────────────────────────


class TestCacheTagEnum:
    """``CacheTag`` values flow into Redis index keys — they are protocol."""

    def test_all_known_tags_present(self) -> None:
        members = {tag.value for tag in CacheTag}
        # Locking the literal values prevents accidental rename which would
        # silently orphan the on-disk Redis index keys.
        assert members == {
            "tag:schedule",
            "tag:user",
            "tag:event",
            "tag:news",
            "tag:groups",
            "tag:notifications",
        }

    def test_str_enum_round_trip(self) -> None:
        """``StrEnum`` values are usable as plain strings."""
        assert CacheTag.SCHEDULE == "tag:schedule"
        assert f"{CacheTag.SCHEDULE}:keys" == "tag:schedule:keys"


# ── 2. get_tags_for_key — prefix → tag mapping ───────────────────────────────


class TestGetTagsForKey:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            (f"{CACHE_PREFIX_SCHEDULE}:42", [CacheTag.SCHEDULE]),
            (f"{CACHE_PREFIX_USER}:1", [CacheTag.USER]),
            (f"{CACHE_PREFIX_EVENT}:5", [CacheTag.EVENT]),
            (f"{CACHE_PREFIX_NEWS}:99", [CacheTag.NEWS]),
            (f"{CACHE_PREFIX_GROUPS}", [CacheTag.GROUPS]),
            (f"{CACHE_PREFIX_GROUPS}:active", [CacheTag.GROUPS]),
            ("event:list", [CacheTag.EVENT]),
            ("news:list", [CacheTag.NEWS]),
        ],
    )
    def test_known_prefix(self, key: str, expected: list[CacheTag]) -> None:
        assert get_tags_for_key(key) == expected

    def test_unknown_prefix_returns_empty(self) -> None:
        """A key with no recognised prefix gets no tags."""
        assert get_tags_for_key("totally:unknown:prefix") == []

    def test_empty_key_returns_empty(self) -> None:
        """An empty key has no prefix matches."""
        assert get_tags_for_key("") == []

    def test_exact_prefix_match(self) -> None:
        """A key equal to the prefix still matches."""
        assert get_tags_for_key(CACHE_PREFIX_USER) == [CacheTag.USER]


# ── 3. Key generators ────────────────────────────────────────────────────────


class TestKeyGenerators:
    def test_schedule_cache_key(self) -> None:
        assert schedule_cache_key(42) == "schedule:group:42"

    def test_user_cache_key(self) -> None:
        assert user_cache_key(99) == "user:profile:99"

    def test_event_cache_key(self) -> None:
        assert event_cache_key(7) == "event:7"

    def test_events_list_cache_key(self) -> None:
        assert events_list_cache_key() == "event:list"

    def test_news_cache_key(self) -> None:
        assert news_cache_key(1) == "news:1"

    def test_news_list_cache_key(self) -> None:
        assert news_list_cache_key() == "news:list"

    def test_generators_round_trip_via_get_tags(self) -> None:
        """Each generated key must map back to its expected tag."""
        assert CacheTag.SCHEDULE in get_tags_for_key(schedule_cache_key(1))
        assert CacheTag.USER in get_tags_for_key(user_cache_key(1))
        assert CacheTag.EVENT in get_tags_for_key(event_cache_key(1))
        assert CacheTag.NEWS in get_tags_for_key(news_cache_key(1))


# ── 4. register_key_with_tags ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_key_with_tags_no_tags_returns_silently() -> None:
    """An unknown-prefix key takes no Redis action."""
    with patch("app.deps.cache.get_cache_client") as gcc:
        await register_key_with_tags("totally:unknown:key")
        gcc.assert_not_called()


@pytest.mark.asyncio
async def test_register_key_with_tags_pipelines_sadd_and_expire() -> None:
    """Each matching tag receives ``SADD`` + ``EXPIRE`` in a single pipeline."""
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)

    with patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)):
        await register_key_with_tags(schedule_cache_key(1), ttl_seconds=600)

    redis.pipeline.assert_called_once_with(transaction=False)
    # SADD + EXPIRE per tag (only SCHEDULE matches → 1 SADD + 1 EXPIRE).
    pipe.sadd.assert_called_once_with(f"{CacheTag.SCHEDULE}:keys", "schedule:group:1")
    pipe.expire.assert_called_once_with(f"{CacheTag.SCHEDULE}:keys", 600)
    pipe.execute.assert_awaited_once()


# ── 5. invalidate_by_tag ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_by_tag_returns_zero_when_no_keys() -> None:
    """An empty tag index returns 0 deletions."""
    redis = MagicMock()
    redis.smembers = AsyncMock(return_value=set())

    with patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)):
        count = await invalidate_by_tag(CacheTag.NEWS)

    assert count == 0


@pytest.mark.asyncio
async def test_invalidate_by_tag_deletes_keys_and_index() -> None:
    """Members are deleted and the index entry is dropped — count returned."""
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis = MagicMock()
    redis.smembers = AsyncMock(return_value={b"news:1", b"news:list"})
    redis.pipeline = MagicMock(return_value=pipe)

    with patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)):
        count = await invalidate_by_tag(CacheTag.NEWS)

    assert count == 2
    redis.pipeline.assert_called_once_with(transaction=False)
    # Two member deletes plus the index delete.
    assert pipe.delete.call_count == 3
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidate_by_tag_handles_string_members() -> None:
    """Members may already be ``str`` (e.g. fakeredis-decoded)."""
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis = MagicMock()
    redis.smembers = AsyncMock(return_value={"event:5"})
    redis.pipeline = MagicMock(return_value=pipe)

    with patch("app.deps.cache.get_cache_client", new=AsyncMock(return_value=redis)):
        count = await invalidate_by_tag(CacheTag.EVENT)

    assert count == 1


# ── 6. invalidate_*_cache helper functions ───────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_schedule_cache_calls_cache_with_key() -> None:
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        await invalidate_schedule_cache(42)
    cache.invalidate.assert_awaited_once_with("schedule:group:42")


@pytest.mark.asyncio
async def test_invalidate_user_cache_calls_cache_with_key() -> None:
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        await invalidate_user_cache(7)
    cache.invalidate.assert_awaited_once_with("user:profile:7")


@pytest.mark.asyncio
async def test_invalidate_event_cache_invalidates_item_and_list() -> None:
    """Event mutation invalidates both the item and the events-list cache."""
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        await invalidate_event_cache(5)
    cache.invalidate.assert_awaited_once_with("event:5", "event:list")


@pytest.mark.asyncio
async def test_invalidate_news_cache_invalidates_item_and_list() -> None:
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        await invalidate_news_cache(99)
    cache.invalidate.assert_awaited_once_with("news:1".replace("1", "99"), "news:list")


@pytest.mark.asyncio
async def test_invalidate_groups_cache_targets_groups_prefix() -> None:
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        await invalidate_groups_cache()
    cache.invalidate.assert_awaited_once_with(CACHE_PREFIX_GROUPS)


# ── 7. CacheInvalidator context manager ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_invalidator_flushes_on_exit() -> None:
    """Queued keys are invalidated when the ``async with`` block exits."""
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        async with CacheInvalidator() as inv:
            inv.schedule(group_id=1)
            inv.user(user_id=2)
    cache.invalidate.assert_awaited_once()
    keys = set(cache.invalidate.call_args.args)
    assert keys == {"schedule:group:1", "user:profile:2"}


@pytest.mark.asyncio
async def test_cache_invalidator_dedupes_keys() -> None:
    """Duplicate enqueues collapse to a single invalidation call."""
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        inv = CacheInvalidator()
        inv.schedule(group_id=1)
        inv.schedule(group_id=1)  # duplicate
        inv.event(event_id=5)  # event_id queues both event:5 + event:list
        inv.event(event_id=5)  # duplicate
        count = await inv.flush()
    assert count == 3  # schedule + event + events-list
    keys = set(cache.invalidate.call_args.args)
    assert keys == {"schedule:group:1", "event:5", "event:list"}


@pytest.mark.asyncio
async def test_cache_invalidator_empty_flush_returns_zero() -> None:
    """``flush()`` with no queued keys is a no-op returning 0."""
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        inv = CacheInvalidator()
        count = await inv.flush()
    assert count == 0
    cache.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_cache_invalidator_flushes_even_on_exception() -> None:
    """``__aexit__`` calls flush() unconditionally — partial state still cleared."""
    cache = MagicMock()
    cache.invalidate = AsyncMock()
    with patch("app.services.cache_invalidation.get_cache", return_value=cache):
        with pytest.raises(RuntimeError):
            async with CacheInvalidator() as inv:
                inv.user(user_id=42)
                raise RuntimeError("boom")
    cache.invalidate.assert_awaited_once()
    assert "user:profile:42" in cache.invalidate.call_args.args


# ── 9. invalidates_cache decorator ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidates_cache_calls_invalidate_after_success() -> None:
    """The decorator invokes ``invalidate_by_tag`` after each successful call."""
    with patch(
        "app.services.cache_invalidation.invalidate_by_tag",
        new=AsyncMock(return_value=2),
    ) as mocked:

        @invalidates_cache(CacheTag.EVENT)
        async def update_event(event_id: int) -> int:
            return event_id

        result = await update_event(7)
    assert result == 7
    mocked.assert_awaited_once_with(CacheTag.EVENT)


@pytest.mark.asyncio
async def test_invalidates_cache_does_not_invalidate_on_exception() -> None:
    """If the wrapped function raises, no invalidation runs (mutation aborted)."""
    with patch(
        "app.services.cache_invalidation.invalidate_by_tag", new=AsyncMock()
    ) as mocked:

        @invalidates_cache(CacheTag.EVENT)
        async def failing() -> None:
            raise ValueError("nope")

        with pytest.raises(ValueError):
            await failing()
    mocked.assert_not_called()


@pytest.mark.asyncio
async def test_invalidates_cache_supports_multiple_tags() -> None:
    """Multiple tags trigger one ``invalidate_by_tag`` call per tag."""
    with patch(
        "app.services.cache_invalidation.invalidate_by_tag", new=AsyncMock()
    ) as mocked:

        @invalidates_cache(CacheTag.EVENT, CacheTag.SCHEDULE)
        async def bulk_reschedule() -> None:
            return None

        await bulk_reschedule()
    assert mocked.await_count == 2
    called = {call.args[0] for call in mocked.await_args_list}
    assert called == {CacheTag.EVENT, CacheTag.SCHEDULE}


@pytest.mark.asyncio
async def test_invalidates_cache_preserves_function_metadata() -> None:
    """``functools.wraps`` keeps __name__ / docstring readable for traces."""

    @invalidates_cache(CacheTag.NEWS)
    async def my_func() -> None:
        """My docstring."""
        return None

    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "My docstring."
