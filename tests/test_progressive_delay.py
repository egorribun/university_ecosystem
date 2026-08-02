"""Unit tests for ProgressiveDelayTracker."""

from __future__ import annotations

import time
import typing
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.ratelimit.delay import (
    PROGRESSIVE_DELAY_MAX,
    PROGRESSIVE_DELAY_STEPS,
    ProgressiveDelayInfo,
    ProgressiveDelayTracker,
    _delay_memory,
    _delay_memory_lock,
    clear_delay_memory,
)
from app.core.ratelimit.fastapi import get_progressive_delay_tracker


def test_clear_delay_memory_removes_all_in_memory_entries():
    _delay_memory["closure-key"] = 4

    clear_delay_memory()

    assert "closure-key" not in _delay_memory


class TestProgressiveDelayCalculation:
    """Tests for delay calculation logic."""

    @pytest.fixture
    def tracker(self) -> ProgressiveDelayTracker:
        return ProgressiveDelayTracker()

    def test_zero_failures_returns_no_delay(self, tracker) -> None:
        """No delay for zero failures."""
        assert tracker._calculate_delay(0) == 0.0

    def test_negative_failures_returns_no_delay(self, tracker) -> None:
        """Negative failures treated as no failures."""
        assert tracker._calculate_delay(-5) == 0.0

    def test_first_failure_returns_first_step(self, tracker) -> None:
        """First failure returns first delay step."""
        assert tracker._calculate_delay(1) == PROGRESSIVE_DELAY_STEPS[0]

    def test_delay_increases_with_failures(self, tracker) -> None:
        """Delay increases progressively with failures."""
        delays = [tracker._calculate_delay(i) for i in range(1, 6)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_delay_capped_at_max(self, tracker) -> None:
        """Delay does not exceed maximum."""
        assert tracker._calculate_delay(100) <= PROGRESSIVE_DELAY_MAX


class TestProgressiveDelayTrackerMemory:
    """Tests for ProgressiveDelayTracker with memory backend."""

    @pytest.fixture(autouse=True)
    async def clear_memory(self) -> typing.AsyncGenerator[None]:
        """Clear memory storage before each test."""
        async with _delay_memory_lock:
            _delay_memory.clear()
        yield
        async with _delay_memory_lock:
            _delay_memory.clear()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_record_failure_increments_count(self) -> None:
        """Record failure increments failure counter."""
        tracker = ProgressiveDelayTracker()
        info1 = await tracker.record_failure("test:user1")
        assert info1.failures == 1
        assert info1.delay_seconds > 0
        assert info1.should_delay is True

        info2 = await tracker.record_failure("test:user1")
        assert info2.failures == 2

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_delay_without_recording(self) -> None:
        """Get delay returns current state without recording."""
        tracker = ProgressiveDelayTracker()
        await tracker.record_failure("test:user2")

        info = await tracker.get_delay("test:user2")
        assert info.failures == 1

        # Should still be 1 after get_delay
        info2 = await tracker.get_delay("test:user2")
        assert info2.failures == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_clears_failures(self) -> None:
        """Reset clears failure count for identifier."""
        tracker = ProgressiveDelayTracker()
        await tracker.record_failure("test:user3")
        await tracker.record_failure("test:user3")

        info = await tracker.get_delay("test:user3")
        assert info.failures == 2

        await tracker.reset("test:user3")

        info_after = await tracker.get_delay("test:user3")
        assert info_after.failures == 0
        assert info_after.should_delay is False

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ttl_expiration_resets_failures(self) -> None:
        """Failures reset after TTL expiration."""
        tracker = ProgressiveDelayTracker(ttl_seconds=1)
        await tracker.record_failure("test:ttl")

        info = await tracker.get_delay("test:ttl")
        assert info.failures == 1

        # Simulate TTL expiration by patching time
        with patch("app.core.ratelimit.delay.time") as mock_time:
            mock_time.time.return_value = time.time() + 2
            info_expired = await tracker.get_delay("test:ttl")
            assert info_expired.failures == 0

    @pytest.mark.asyncio(loop_scope="session")
    async def test_different_identifiers_independent(self) -> None:
        """Different identifiers have independent counters."""
        tracker = ProgressiveDelayTracker()
        await tracker.record_failure("ip:1.1.1.1")
        await tracker.record_failure("ip:1.1.1.1")
        await tracker.record_failure("ip:2.2.2.2")

        info1 = await tracker.get_delay("ip:1.1.1.1")
        info2 = await tracker.get_delay("ip:2.2.2.2")

        assert info1.failures == 2
        assert info2.failures == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_apply_delay_if_needed_applies_delay(self) -> None:
        """Apply delay if needed actually waits."""
        tracker = ProgressiveDelayTracker()
        await tracker.record_failure("test:delay")

        # start = time.time()
        with patch.object(tracker, "get_delay") as mock_get:
            mock_get.return_value = ProgressiveDelayInfo(
                failures=1, delay_seconds=0.01, should_delay=True
            )
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await tracker.apply_delay_if_needed("test:delay")
                mock_sleep.assert_called_once_with(0.01)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_apply_delay_if_needed_no_delay_when_zero(self) -> None:
        """No sleep called when delay is zero."""
        tracker = ProgressiveDelayTracker()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            info = await tracker.apply_delay_if_needed("test:no_failure")
            mock_sleep.assert_not_called()
            assert info.should_delay is False

    @pytest.mark.asyncio(loop_scope="session")
    async def test_memory_pruning_on_failure(self) -> None:
        """Memory backend prunes stale items on failure recording."""
        tracker = ProgressiveDelayTracker(ttl_seconds=1)
        async with _delay_memory_lock:
            _delay_memory["test:stale"] = (1, time.time() - 10.0)

        from app.core.ratelimit import delay as delay_module

        with patch.object(delay_module, "_delay_memory_last_cleanup", 0.0):
            await tracker.record_failure("test:new_req")

        async with _delay_memory_lock:
            assert "test:stale" not in _delay_memory


class TestProgressiveDelayTrackerRedis:
    """Tests for ProgressiveDelayTracker with Redis backend."""

    @pytest.fixture
    def mock_redis_client(self) -> MagicMock:
        """Create mock Redis client."""
        client = MagicMock()
        client.incr = AsyncMock(return_value=1)
        client.expire = AsyncMock()
        client.get = AsyncMock(return_value=b"1")
        client.delete = AsyncMock()

        # Mock pipeline
        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        client.pipeline.return_value = mock_pipe

        return client

    @pytest.mark.asyncio(loop_scope="session")
    async def test_record_failure_uses_redis(
        self, mock_redis_client: MagicMock
    ) -> None:
        """Record failure uses Redis when URL provided."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        with patch(
            "app.core.ratelimit.delay.get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            info = await tracker.record_failure("test:redis1")

            mock_pipe = mock_redis_client.pipeline.return_value
            mock_pipe.incr.assert_called_once()
            mock_pipe.expire.assert_called_once()
            mock_pipe.execute.assert_called_once()
            assert info.failures == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_redis_fallback_on_error(self) -> None:
        """Falls back to memory on Redis error."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        async def failing_get_client(url):
            raise RedisError("Connection failed")

        with patch(
            "app.core.ratelimit.delay.get_shared_client",
            side_effect=failing_get_client,
        ):
            # Should fall back to memory without raising
            info = await tracker.record_failure("test:fallback")
            assert info.failures == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_delay_redis(self, mock_redis_client: MagicMock) -> None:
        """Get delay reads from Redis."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")
        mock_redis_client.get = AsyncMock(return_value=b"3")

        with patch(
            "app.core.ratelimit.delay.get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            info = await tracker.get_delay("test:get_redis")
            assert info.failures == 3

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_redis(self, mock_redis_client: MagicMock) -> None:
        """Reset deletes from Redis."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        with patch(
            "app.core.ratelimit.delay.get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            await tracker.reset("test:reset_redis")
            mock_redis_client.delete.assert_called_once()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_delay_redis_none(self, mock_redis_client: MagicMock) -> None:
        """Get delay when Redis returns None (no failures)."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")
        mock_redis_client.get = AsyncMock(return_value=None)

        with patch(
            "app.core.ratelimit.delay.get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            info = await tracker.get_delay("test:get_redis_none")
            assert info.failures == 0

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_delay_redis_error_fallback(self) -> None:
        """Get delay falls back to memory on RedisError."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")
        async with _delay_memory_lock:
            _delay_memory[tracker._make_key("test:fb_get")] = (4, time.time())

        async def failing_get(key):
            raise RedisError("Connection failure")

        with patch("app.core.ratelimit.delay.get_shared_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get = failing_get
            mock_get_client.return_value = mock_client

            info = await tracker.get_delay("test:fb_get")
            assert info.failures == 4

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_redis_error_swallowed(self) -> None:
        """Reset swallows RedisError/OSError and pops local memory."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")
        async with _delay_memory_lock:
            _delay_memory[tracker._make_key("test:fb_reset")] = (2, time.time())

        async def failing_delete(key):
            raise OSError("OS connection refused")

        with patch("app.core.ratelimit.delay.get_shared_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.delete = failing_delete
            mock_get_client.return_value = mock_client

            await tracker.reset("test:fb_reset")
            # should still pop local memory
            async with _delay_memory_lock:
                assert tracker._make_key("test:fb_reset") not in _delay_memory


class TestProgressiveDelayTrackerConfig:
    """Tests for ProgressiveDelayTracker configuration."""

    def test_custom_delay_steps(self) -> None:
        """Custom delay steps are respected."""
        tracker = ProgressiveDelayTracker(delay_steps=(0.1, 0.2, 0.5))
        assert tracker._delay_steps == (0.1, 0.2, 0.5)

    def test_custom_max_delay(self) -> None:
        """Custom max delay is respected."""
        tracker = ProgressiveDelayTracker(max_delay=5.0)
        assert tracker._max_delay == 5.0

    def test_custom_ttl(self) -> None:
        """Custom TTL is respected."""
        tracker = ProgressiveDelayTracker(ttl_seconds=60)
        assert tracker._ttl == 60

    def test_custom_key_prefix(self) -> None:
        """Custom key prefix is used."""
        tracker = ProgressiveDelayTracker(key_prefix="custom-prefix")
        key = tracker._make_key("test")
        assert key == "custom-prefix:test"


class TestGlobalProgressiveDelayTracker:
    """Tests for global tracker instance."""

    def test_get_progressive_delay_tracker_returns_instance(self) -> None:
        """Global getter returns tracker instance."""
        tracker = get_progressive_delay_tracker()
        assert isinstance(tracker, ProgressiveDelayTracker)

    def test_get_progressive_delay_tracker_factory(self) -> None:
        """New instance returned on subsequent calls for test isolation."""
        tracker1 = get_progressive_delay_tracker()
        tracker2 = get_progressive_delay_tracker()
        assert tracker1 is not tracker2
        assert isinstance(tracker1, ProgressiveDelayTracker)
        assert isinstance(tracker2, ProgressiveDelayTracker)
