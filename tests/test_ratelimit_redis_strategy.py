"""Unit tests for the Redis sliding-window rate-limit strategy
(app/core/ratelimit/strategies/redis.py).

Hermetic — a fake client is injected via ``set_rate_limit_client_factory`` (no real
Redis). fakeredis cannot execute Lua/EVALSHA, so the EVALSHA *happy path* is driven
with an ``AsyncMock`` returning canned result vectors; the NoScriptError / Redis-Cluster
"unknown command" / re-raise branches are exercised by configuring the mock's
``side_effect``. Module-global SHA cache + the shared-client pool are reset per test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import redis.exceptions as rexc
from redis.exceptions import NoScriptError, ResponseError

from app.core.ratelimit.exceptions import RateLimitStorageUnavailable
from app.core.ratelimit.strategies import base
from app.core.ratelimit.strategies import redis as redis_strat
from app.core.ratelimit.strategies.base import set_rate_limit_client_factory

URL = "redis://localhost"


@pytest.fixture(autouse=True)
def _reset_redis_strategy_state():
    base._shared_clients.clear()
    base._shared_clients_write_lock = None
    redis_strat._RATE_LIMIT_SHA = None
    yield
    set_rate_limit_client_factory(None)
    base._shared_clients.clear()
    base._shared_clients_write_lock = None
    redis_strat._RATE_LIMIT_SHA = None


def _install(fake) -> None:
    set_rate_limit_client_factory(lambda _url: fake)


def _strategy() -> redis_strat.RedisSlidingWindowStrategy:
    return redis_strat.RedisSlidingWindowStrategy(URL)


@pytest.mark.asyncio
async def test_check_zero_limit_or_window_short_circuits():
    # No client touched — returns before get_shared_client.
    info = await _strategy().check("k", 0, 60)
    assert info.allowed is True and info.retry_after == 0
    info2 = await _strategy().check("k", 5, 0)
    assert info2.allowed is True


@pytest.mark.asyncio
async def test_check_allowed_happy_path_via_evalsha():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.return_value = [1, 5, 0]
    _install(fake)

    info = await _strategy().check("user:1", 10, 60)

    assert info.allowed is True
    assert info.remaining == 5
    assert info.retry_after == 0
    fake.evalsha.assert_awaited_once()
    fake.eval.assert_not_called()


@pytest.mark.asyncio
async def test_check_denied_ceils_retry_after_from_ms():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.return_value = [0, 0, 2500]  # 2500 ms → ceil(2.5) == 3 s
    _install(fake)

    info = await _strategy().check("user:1", 10, 60)

    assert info.allowed is False
    assert info.remaining == 0
    assert info.retry_after == 3


@pytest.mark.asyncio
async def test_check_noscript_invalidates_sha_and_falls_back_to_eval():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.side_effect = NoScriptError("NOSCRIPT No matching script")
    fake.eval.return_value = [1, 4, 0]
    _install(fake)

    info = await _strategy().check("user:1", 10, 60)

    assert info.allowed is True
    assert info.remaining == 4
    fake.eval.assert_awaited_once()
    assert redis_strat._RATE_LIMIT_SHA is None  # invalidated under lock


@pytest.mark.asyncio
async def test_check_cluster_unknown_command_raises_storage_unavailable():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.side_effect = ResponseError("unknown command 'EVALSHA'")
    _install(fake)

    with pytest.raises(RateLimitStorageUnavailable):
        await _strategy().check("user:1", 10, 60)


@pytest.mark.asyncio
async def test_check_err_prefixed_response_error_raises_storage_unavailable():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.side_effect = ResponseError("ERR This Redis command is not allowed")
    _install(fake)

    with pytest.raises(RateLimitStorageUnavailable):
        await _strategy().check("user:1", 10, 60)


@pytest.mark.asyncio
async def test_check_unrelated_response_error_is_reraised():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.side_effect = ResponseError("WRONGTYPE Operation against a key")
    _install(fake)

    with pytest.raises(ResponseError):
        await _strategy().check("user:1", 10, 60)


@pytest.mark.asyncio
async def test_check_connection_error_is_reraised():
    fake = AsyncMock()
    fake.script_load.return_value = "sha-abc"
    fake.evalsha.side_effect = rexc.ConnectionError("connection refused")
    _install(fake)

    with pytest.raises(rexc.ConnectionError):
        await _strategy().check("user:1", 10, 60)
