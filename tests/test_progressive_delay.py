"""Unit tests for ProgressiveDelayTracker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.rate_limit import (
    PROGRESSIVE_DELAY_MAX,
    PROGRESSIVE_DELAY_STEPS,
    ProgressiveDelayInfo,
    ProgressiveDelayTracker,
    _calculate_delay,
    _progressive_delay_memory,
    _progressive_delay_memory_lock,
    get_progressive_delay_tracker,
)


class TestProgressiveDelayCalculation:
    """Tests for delay calculation logic."""

    def test_zero_failures_returns_no_delay(self) -> None:
        """No delay for zero failures."""
        assert _calculate_delay(0) == 0.0

    def test_negative_failures_returns_no_delay(self) -> None:
        """Negative failures treated as no failures."""
        assert _calculate_delay(-5) == 0.0

    def test_first_failure_returns_first_step(self) -> None:
        """First failure returns first delay step."""
        assert _calculate_delay(1) == PROGRESSIVE_DELAY_STEPS[0]

    def test_delay_increases_with_failures(self) -> None:
        """Delay increases progressively with failures."""
        delays = [_calculate_delay(i) for i in range(1, 6)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_delay_capped_at_max(self) -> None:
        """Delay does not exceed maximum."""
        assert _calculate_delay(100) <= PROGRESSIVE_DELAY_MAX


class TestProgressiveDelayTrackerMemory:
    """Tests for ProgressiveDelayTracker with memory backend."""

    @pytest.fixture(autouse=True)
    async def clear_memory(self) -> None:
        """Clear memory storage before each test."""
        async with _progressive_delay_memory_lock:
            _progressive_delay_memory.clear()
        yield
        async with _progressive_delay_memory_lock:
            _progressive_delay_memory.clear()

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
        with patch("app.core.rate_limit.time") as mock_time:
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
        return client

    @pytest.mark.asyncio(loop_scope="session")
    async def test_record_failure_uses_redis(
        self, mock_redis_client: MagicMock
    ) -> None:
        """Record failure uses Redis when URL provided."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        with patch(
            "app.core.rate_limit._get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            info = await tracker.record_failure("test:redis1")

            mock_redis_client.incr.assert_called_once()
            mock_redis_client.expire.assert_called_once()
            assert info.failures == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_redis_fallback_on_error(self) -> None:
        """Falls back to memory on Redis error."""
        tracker = ProgressiveDelayTracker(redis_url="redis://localhost:6379")

        async def failing_get_client(url):
            raise RedisError("Connection failed")

        with patch(
            "app.core.rate_limit._get_shared_client",
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
            "app.core.rate_limit._get_shared_client",
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
            "app.core.rate_limit._get_shared_client",
            new_callable=AsyncMock,
            return_value=mock_redis_client,
        ):
            await tracker.reset("test:reset_redis")
            mock_redis_client.delete.assert_called_once()


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

    def test_get_progressive_delay_tracker_singleton(self) -> None:
        """Same instance returned on subsequent calls."""
        tracker1 = get_progressive_delay_tracker()
        tracker2 = get_progressive_delay_tracker()
        assert tracker1 is tracker2
