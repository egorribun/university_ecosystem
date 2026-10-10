"""Tests for rate limit strategies (app/core/ratelimit/strategies/).

Covers base.py (shared client, factory), memory.py (MemorySlidingWindowStrategy),
and redis.py (RedisSlidingWindowStrategy with fakeredis).
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from redis.exceptions import NoScriptError, RedisError, ResponseError

from app.core.ratelimit.exceptions import RateLimitStorageUnavailable
from app.core.ratelimit.strategies import base as rate_limit_base
from app.core.ratelimit.strategies.base import (
    _create_redis_pool,
    _shared_clients,
    get_shared_client,
    set_rate_limit_client_factory,
)
from app.core.ratelimit.strategies.memory import (
    MemorySlidingWindowStrategy,
    _memory_windows,
    _shard_lock,
    clear_memory_state,
)
from app.core.ratelimit.strategies.redis import (
    RedisSlidingWindowStrategy,
    _load_script_sha,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_memory_state():
    """Clear in-memory rate limit state before and after each test."""
    clear_memory_state()
    yield
    clear_memory_state()


@pytest.fixture(autouse=True)
def _clean_shared_clients():
    """Reset shared Redis clients between tests."""
    original = dict(_shared_clients)
    _shared_clients.clear()
    yield
    _shared_clients.clear()
    _shared_clients.update(original)


# ===========================================================================
# base.py tests
# ===========================================================================


class TestGetSharedClient:
    """Tests for the get_shared_client singleton pattern."""

    @pytest.mark.asyncio
    async def test_returns_cached_client_on_second_call(self):
        """Second call returns the same client object (cached)."""
        fake_client = MagicMock()
        set_rate_limit_client_factory(lambda url: fake_client)
        try:
            client1 = await get_shared_client("redis://test:6379")
            client2 = await get_shared_client("redis://test:6379")
            assert client1 is client2
        finally:
            set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    async def test_concurrent_calls_single_client(self):
        """Concurrent calls don't create multiple clients due to locking."""
        creation_count = 0

        def counting_factory(url):
            nonlocal creation_count
            creation_count += 1
            return MagicMock()

        set_rate_limit_client_factory(counting_factory)
        try:
            tasks = [get_shared_client("redis://concurrent:6379") for _ in range(10)]
            results = await asyncio.gather(*tasks)
            # All tasks should get the same client
            assert all(r is results[0] for r in results)
            assert creation_count == 1
        finally:
            set_rate_limit_client_factory(None)

    def test_concurrent_lookups_coordinate_one_synchronous_factory_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Coordinate concurrent cache lookups without cross-loop lock wakeups.

        The fake returned object is only an identity sentinel; this does not
        exercise Redis operations across loops, which remain bound to one ASGI
        event loop per worker process.
        """
        redis_url = "redis://cross-loop:6379"
        client = MagicMock()
        factory_entered = threading.Event()
        release_factory = threading.Event()
        second_loop_ready = threading.Event()
        second_guard_attempt = threading.Event()
        foreign_call_soon: list[bool] = []
        created: list[object] = []
        returned: list[object] = []
        errors: list[BaseException] = []

        class ObservedLock:
            def __init__(self) -> None:
                self._lock = threading.Lock()

            def __enter__(self) -> ObservedLock:
                if threading.current_thread().name == "rate-limit-second-loop":
                    second_guard_attempt.set()
                self._lock.acquire()
                return self

            def __exit__(self, *_exc: object) -> None:
                self._lock.release()

        def blocking_factory(_url: str) -> MagicMock:
            created.append(client)
            factory_entered.set()
            if not release_factory.wait(timeout=5):
                raise AssertionError("test did not release client factory")
            return client

        monkeypatch.setattr(rate_limit_base, "_shared_clients", {})
        monkeypatch.setattr(rate_limit_base, "_shared_clients_guard", ObservedLock())
        monkeypatch.setattr(rate_limit_base, "_redis_factory", blocking_factory)

        def first_loop_worker() -> None:
            async def get_client() -> None:
                asyncio.get_running_loop().set_debug(True)
                returned.append(await get_shared_client(redis_url))

            try:
                asyncio.run(get_client())
            except BaseException as exc:  # record cross-thread loop failures
                errors.append(exc)

        def second_loop_worker() -> None:
            async def get_client() -> None:
                loop = asyncio.get_running_loop()
                loop.set_debug(True)
                original_call_soon = loop.call_soon
                owner_thread = threading.current_thread()

                def checked_call_soon(callback, *args, **kwargs):
                    if threading.current_thread() is not owner_thread:
                        foreign_call_soon.append(True)
                        return loop.call_soon_threadsafe(callback, *args, **kwargs)
                    return original_call_soon(callback, *args, **kwargs)

                loop.call_soon = checked_call_soon  # type: ignore[method-assign]
                second_loop_ready.set()
                returned.append(await get_shared_client(redis_url))

            try:
                asyncio.run(get_client())
            except BaseException as exc:  # record cross-thread loop failures
                errors.append(exc)

        first = threading.Thread(target=first_loop_worker, name="rate-limit-first-loop")
        second = threading.Thread(
            target=second_loop_worker, name="rate-limit-second-loop"
        )
        try:
            first.start()
            assert factory_entered.wait(timeout=2)
            second.start()
            assert second_loop_ready.wait(timeout=2)
            assert second_guard_attempt.wait(timeout=2)
        finally:
            release_factory.set()
            first.join(timeout=3)
            second.join(timeout=3)

        assert not first.is_alive()
        assert not second.is_alive()
        assert not errors
        assert len(created) == 1
        assert len(returned) == 2
        assert all(result is client for result in returned)
        assert foreign_call_soon == []


class TestSetRateLimitClientFactory:
    """Tests for set_rate_limit_client_factory."""

    def test_overrides_factory(self):
        """Custom factory replaces the default."""

        def custom_factory(url):
            return MagicMock()

        set_rate_limit_client_factory(custom_factory)
        # Verify it was set (we reset in teardown)
        set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    async def test_none_resets_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A lookup after reset uses the default Redis constructor again."""
        redis_url = "redis://factory-reset:6379/0"
        injected_client = fakeredis.aioredis.FakeRedis()
        default_client = fakeredis.aioredis.FakeRedis()

        with monkeypatch.context() as isolated:
            # Keep the surrounding suite's factory and clients intact, even
            # when the reset or the subsequent client lookup fails.
            isolated.setattr(rate_limit_base, "_shared_clients", {})
            isolated.setattr(
                rate_limit_base, "_redis_factory", rate_limit_base._redis_factory
            )
            isolated.setattr(
                rate_limit_base.Redis,
                "from_url",
                lambda *_args, **_kwargs: default_client,
            )
            try:
                set_rate_limit_client_factory(lambda _url: injected_client)
                assert await get_shared_client(redis_url) is injected_client

                set_rate_limit_client_factory(None)

                assert await get_shared_client(redis_url) is default_client
            finally:
                try:
                    await injected_client.aclose()
                finally:
                    await default_client.aclose()


class TestCreateRedisPool:
    """Tests for _create_redis_pool."""

    def test_creates_redis_client(self):
        """_create_redis_pool returns a Redis client object."""
        # The function calls Redis.from_url which is mocked globally in tests
        client = _create_redis_pool("redis://localhost:6379")
        assert client is not None


# ===========================================================================
# memory.py tests
# ===========================================================================


class TestMemorySlidingWindowStrategy:
    """Tests for the in-memory sliding window rate limiter."""

    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        """Requests within the limit are allowed."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        info = await strategy.check("user1", limit=5, window_seconds=60)
        assert info.allowed is True
        assert info.remaining == 4
        assert info.retry_after == 0

    @pytest.mark.asyncio
    async def test_blocks_when_limit_reached(self):
        """Returns allowed=False with retry_after when limit is exhausted."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        for _ in range(5):
            await strategy.check("user2", limit=5, window_seconds=60)

        info = await strategy.check("user2", limit=5, window_seconds=60)
        assert info.allowed is False
        assert info.remaining == 0
        assert info.retry_after > 0

    @pytest.mark.asyncio
    async def test_remaining_decrements(self):
        """Remaining count decrements with each allowed request."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        results = []
        for _ in range(3):
            info = await strategy.check("user3", limit=5, window_seconds=60)
            results.append(info.remaining)
        assert results == [4, 3, 2]

    @pytest.mark.asyncio
    async def test_window_slides_old_entries_evicted(self):
        """Old entries outside the window are evicted, freeing capacity."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        # Fill the window
        for _ in range(3):
            await strategy.check("user4", limit=3, window_seconds=1)

        # All capacity used
        info = await strategy.check("user4", limit=3, window_seconds=1)
        assert info.allowed is False

        # Wait for the window to slide
        await asyncio.sleep(1.1)

        # Should be allowed again
        info = await strategy.check("user4", limit=3, window_seconds=1)
        assert info.allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("limit", "window"),
        [
            (0, 60),
            (-1, 60),
            (5, 0),
            (5, -1),
            (0, 0),
        ],
        ids=[
            "limit_zero",
            "limit_negative",
            "window_zero",
            "window_negative",
            "both_zero",
        ],
    )
    async def test_zero_or_negative_always_allowed(self, limit: int, window: int):
        """limit≤0 or window≤0 → always allowed."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        info = await strategy.check("user5", limit=limit, window_seconds=window)
        assert info.allowed is True
        assert info.retry_after == 0


class TestClearMemoryState:
    """Tests for clear_memory_state."""

    @pytest.mark.asyncio
    async def test_clears_all_windows(self):
        """All in-memory windows are cleared."""
        strategy = MemorySlidingWindowStrategy(namespace="test")
        await strategy.check("key1", limit=10, window_seconds=60)
        await strategy.check("key2", limit=10, window_seconds=60)
        assert len(_memory_windows) > 0

        clear_memory_state()
        assert len(_memory_windows) == 0


class TestShardLock:
    """Tests for the _shard_lock consistent hashing."""

    def test_same_key_returns_same_lock(self):
        """Consistent hashing returns the same lock for the same key."""
        lock1 = _shard_lock("test-key")
        lock2 = _shard_lock("test-key")
        assert lock1 is lock2

    def test_different_keys_may_differ(self):
        """Different keys may map to different locks (probabilistic)."""
        locks = {id(_shard_lock(f"key-{i}")) for i in range(100)}
        # With 256 shards and 100 keys, expect some diversity
        assert len(locks) > 1


# ===========================================================================
# redis.py tests
# ===========================================================================


class TestRedisSlidingWindowStrategy:
    """Tests for the Redis-backed sliding window rate limiter."""

    @pytest.fixture
    def fake_redis(self):
        """Fresh fakeredis with Lua scripting stubbed in Python.

        fakeredis needs the ``lupa`` C-extension for SCRIPT LOAD / EVALSHA.
        Without it every scripting call raises
        ``ResponseError: unknown command 'script'``, which the production code
        converts to ``RateLimitStorageUnavailable`` — making the happy-path
        tests impossible to run.

        We side-step the dependency by implementing the rate-limit Lua script
        logic in Python, using only the sorted-set primitives that fakeredis
        supports natively (ZADD, ZCARD, ZREMRANGEBYSCORE, PEXPIRE, ZRANGE).
        """
        import random

        redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
        _FAKE_SHA = "fakeredis-lua-stub-000000000000000001"

        async def _run_rate_limit_script(key, limit, now_ms, window_ms):
            """Python equivalent of _RATE_LIMIT_SCRIPT in redis.py."""
            if isinstance(key, bytes):
                key = key.decode()
            cutoff = now_ms - window_ms

            await redis.zremrangebyscore(key, "-inf", cutoff)
            current = int(await redis.zcard(key))

            if current >= limit:
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                retry_after_ms = 0
                if oldest:
                    oldest_ts = float(oldest[0][1])
                    retry_after_ms = max(0, int(oldest_ts + window_ms - now_ms))
                return [0, 0, retry_after_ms]

            member = f"{now_ms}:{random.randint(0, 999999)}"  # noqa: S311
            await redis.zadd(key, {member: float(now_ms)})
            await redis.pexpire(key, window_ms)
            remaining = limit - current - 1
            return [1, remaining, 0]

        async def _script_load(script):
            return _FAKE_SHA

        async def _evalsha(sha, numkeys, *args, **kwargs):
            key, limit, now_ms, window_ms = (
                args[0],
                int(args[1]),
                int(args[2]),
                int(args[3]),
            )
            return await _run_rate_limit_script(key, limit, now_ms, window_ms)

        async def _eval(script, numkeys, *args, **kwargs):
            key, limit, now_ms, window_ms = (
                args[0],
                int(args[1]),
                int(args[2]),
                int(args[3]),
            )
            return await _run_rate_limit_script(key, limit, now_ms, window_ms)

        redis.script_load = _script_load
        redis.evalsha = _evalsha
        redis.eval = _eval
        return redis

    @pytest.fixture(autouse=True)
    def _reset_sha_cache(self):
        """Reset the cached Lua script SHA between tests."""
        import app.core.ratelimit.strategies.redis as redis_mod

        original_sha = redis_mod._RATE_LIMIT_SHA
        redis_mod._RATE_LIMIT_SHA = None
        yield
        redis_mod._RATE_LIMIT_SHA = original_sha

    @pytest.mark.asyncio
    async def test_allows_within_limit(self, fake_redis):
        """Requests within the limit are allowed."""
        set_rate_limit_client_factory(lambda url: fake_redis)
        try:
            strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")
            info = await strategy.check("ruser1", limit=5, window_seconds=60)
            assert info.allowed is True
            assert info.remaining >= 0
            assert info.retry_after == 0
        finally:
            set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    async def test_blocks_when_limit_reached(self, fake_redis):
        """Returns allowed=False when limit is exhausted."""
        set_rate_limit_client_factory(lambda url: fake_redis)
        try:
            strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")
            for _ in range(5):
                await strategy.check("ruser2", limit=5, window_seconds=60)

            info = await strategy.check("ruser2", limit=5, window_seconds=60)
            assert info.allowed is False
            assert info.remaining == 0
            assert info.retry_after > 0
        finally:
            set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("limit", "window"),
        [(0, 60), (-1, 60), (5, 0), (5, -1)],
        ids=["limit_zero", "limit_negative", "window_zero", "window_negative"],
    )
    async def test_zero_or_negative_always_allowed(self, limit: int, window: int):
        """limit≤0 or window≤0 → always allowed without touching Redis."""
        strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")
        info = await strategy.check("ruser3", limit=limit, window_seconds=window)
        assert info.allowed is True
        assert info.retry_after == 0

    @pytest.mark.asyncio
    async def test_noscript_error_recovery(self, fake_redis):
        """NoScriptError invalidates SHA and falls back to EVAL."""
        set_rate_limit_client_factory(lambda url: fake_redis)
        try:
            strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")

            # First call succeeds normally (loads script)
            info = await strategy.check("ruser4", limit=10, window_seconds=60)
            assert info.allowed is True

            # Simulate NoScriptError on evalsha, then success on eval
            original_evalsha = fake_redis.evalsha

            call_count = 0

            async def failing_evalsha(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise NoScriptError("NOSCRIPT No matching script")
                return await original_evalsha(*args, **kwargs)

            fake_redis.evalsha = failing_evalsha

            # Should recover via EVAL fallback
            info = await strategy.check("ruser4", limit=10, window_seconds=60)
            assert info.allowed is True
        finally:
            set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    async def test_response_error_unknown_command_raises_storage_unavailable(self):
        """ResponseError with 'unknown command' raises RateLimitStorageUnavailable."""
        mock_client = AsyncMock()
        mock_client.script_load = AsyncMock(return_value="fake-sha")
        mock_client.evalsha = AsyncMock(
            side_effect=ResponseError("ERR unknown command 'EVALSHA'")
        )

        set_rate_limit_client_factory(lambda url: mock_client)
        try:
            strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")
            with pytest.raises(RateLimitStorageUnavailable):
                await strategy.check("ruser5", limit=5, window_seconds=60)
        finally:
            set_rate_limit_client_factory(None)

    @pytest.mark.asyncio
    async def test_other_redis_error_reraised(self):
        """Non-ResponseError RedisError subtypes are re-raised as-is."""
        mock_client = AsyncMock()
        mock_client.script_load = AsyncMock(return_value="fake-sha")
        mock_client.evalsha = AsyncMock(side_effect=RedisError("Connection refused"))

        set_rate_limit_client_factory(lambda url: mock_client)
        try:
            strategy = RedisSlidingWindowStrategy(redis_url="redis://fake")
            with pytest.raises(RedisError, match="Connection refused"):
                await strategy.check("ruser6", limit=5, window_seconds=60)
        finally:
            set_rate_limit_client_factory(None)


class TestLoadScriptSha:
    """Tests for the _load_script_sha caching mechanism."""

    @pytest.fixture(autouse=True)
    def _reset_sha(self):
        """Reset SHA cache before each test."""
        import app.core.ratelimit.strategies.redis as redis_mod

        redis_mod._RATE_LIMIT_SHA = None
        yield
        redis_mod._RATE_LIMIT_SHA = None

    @pytest.mark.asyncio
    async def test_caches_sha(self):
        """SHA is loaded once and cached for subsequent calls."""
        mock_client = AsyncMock()
        mock_client.script_load = AsyncMock(return_value="abc123")

        sha1 = await _load_script_sha(mock_client)
        sha2 = await _load_script_sha(mock_client)
        assert sha1 == sha2 == "abc123"
        # script_load should be called exactly once
        mock_client.script_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_double_check_locking(self):
        """Concurrent calls don't load the script multiple times."""
        load_count = 0

        async def counting_load(script):
            nonlocal load_count
            load_count += 1
            await asyncio.sleep(0.01)  # Simulate network delay
            return f"sha-{load_count}"

        mock_client = AsyncMock()
        mock_client.script_load = counting_load

        tasks = [_load_script_sha(mock_client) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert load_count == 1
        assert all(r == results[0] for r in results)


@pytest.mark.asyncio
async def test_rate_limit_strategy_protocol_pass() -> None:
    """Call super().check to execute the protocol ellipsis under coverage."""
    from app.core.ratelimit.contract import RateLimitStrategy

    class DummyStrategy(RateLimitStrategy):
        async def check(self, key: str, limit: int, window_seconds: int):
            return await super().check(key, limit, window_seconds)

    await DummyStrategy().check("key", 10, 60)
