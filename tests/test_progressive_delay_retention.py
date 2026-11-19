"""Cross-instance retention contract for the progressive delay memory backend."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from app.core.ratelimit import delay


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(delay.time, "time", lambda: now[0])
    monkeypatch.setattr(delay, "_delay_memory", {})
    monkeypatch.setattr(delay, "_delay_memory_last_cleanup", 0.0)
    return now


def sweep(clock, monkeypatch, at):
    clock[0] = at
    monkeypatch.setattr(delay, "_delay_memory_last_cleanup", 0.0)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("redis_failure", [False, True])
async def test_short_tracker_cleanup_preserves_other_live_ttl(
    clock, monkeypatch, redis_failure
):
    url = "redis://localhost:6379" if redis_failure else None
    if redis_failure:
        monkeypatch.setattr(
            delay, "get_shared_client", AsyncMock(side_effect=RedisError("unavailable"))
        )
    long = delay.ProgressiveDelayTracker(
        redis_url=url, ttl_seconds=900, key_prefix="long"
    )
    short = delay.ProgressiveDelayTracker(
        redis_url=url, ttl_seconds=60, key_prefix="short"
    )
    await long.record_failure("subject")
    await long.record_failure("subject")
    await short.record_failure("expired")

    sweep(clock, monkeypatch, 1301.0)
    await short.record_failure("trigger")

    assert short._make_key("expired") not in delay._delay_memory
    assert (await long.get_delay("subject")).failures == 2
    assert (await long.record_failure("subject")).failures == 3


@pytest.mark.asyncio(loop_scope="session")
async def test_cleanup_uses_each_entry_expiry_and_preserves_strict_boundary(
    clock, monkeypatch
):
    long = delay.ProgressiveDelayTracker(ttl_seconds=900, key_prefix="long")
    short = delay.ProgressiveDelayTracker(ttl_seconds=60, key_prefix="short")
    await long.record_failure("subject")

    sweep(clock, monkeypatch, 1900.0)
    await short.record_failure("trigger")
    assert (await long.get_delay("subject")).failures == 1

    sweep(clock, monkeypatch, 1900.001)
    await short.record_failure("trigger")
    assert long._make_key("subject") not in delay._delay_memory
    assert (await long.get_delay("subject")).failures == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_repeated_failure_refreshes_entry_retention(clock, monkeypatch):
    long = delay.ProgressiveDelayTracker(ttl_seconds=900, key_prefix="long")
    short = delay.ProgressiveDelayTracker(ttl_seconds=60, key_prefix="short")
    await long.record_failure("subject")
    clock[0] = 1800.0
    assert (await long.record_failure("subject")).failures == 2

    sweep(clock, monkeypatch, 2000.0)
    await short.record_failure("trigger")
    assert (await long.get_delay("subject")).failures == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_same_key_keeps_caller_ttl_and_known_retention(clock, monkeypatch):
    long = delay.ProgressiveDelayTracker(ttl_seconds=900, key_prefix="shared")
    short = delay.ProgressiveDelayTracker(ttl_seconds=60, key_prefix="shared")
    sweeper = delay.ProgressiveDelayTracker(ttl_seconds=10, key_prefix="other")
    await long.record_failure("subject")
    clock[0] = 1030.0
    assert (await short.record_failure("subject")).failures == 2

    sweep(clock, monkeypatch, 1301.0)
    await sweeper.record_failure("trigger")
    assert (await short.get_delay("subject")).failures == 0
    assert (await long.get_delay("subject")).failures == 2
    # Caller TTL still resets the counter when writing an expired view.
    assert (await short.record_failure("subject")).failures == 1

    sweep(clock, monkeypatch, 1400.0)
    await sweeper.record_failure("trigger")
    assert long._make_key("subject") not in delay._delay_memory


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("clear_all", [False, True])
async def test_reset_drops_retention_with_counter(clock, monkeypatch, clear_all):
    long = delay.ProgressiveDelayTracker(ttl_seconds=900, key_prefix="shared")
    short = delay.ProgressiveDelayTracker(ttl_seconds=60, key_prefix="shared")
    await long.record_failure("subject")
    if clear_all:
        delay.clear_delay_memory()
    else:
        await long.reset("subject")
    assert (await short.record_failure("subject")).failures == 1

    sweep(clock, monkeypatch, 1301.0)
    await short.record_failure("trigger")
    assert short._make_key("subject") not in delay._delay_memory


@pytest.mark.asyncio(loop_scope="session")
async def test_legacy_entries_use_default_retention_not_sweeper_ttl(clock, monkeypatch):
    short = delay.ProgressiveDelayTracker(ttl_seconds=60, key_prefix="short")
    normal = delay.ProgressiveDelayTracker(key_prefix="legacy")
    delay._delay_memory[normal._make_key("subject")] = (2, clock[0])

    sweep(clock, monkeypatch, 1301.0)
    await short.record_failure("trigger")
    assert (await normal.get_delay("subject")).failures == 2

    sweep(clock, monkeypatch, 1900.001)
    await short.record_failure("trigger")
    assert normal._make_key("subject") not in delay._delay_memory
