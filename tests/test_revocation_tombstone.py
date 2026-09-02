from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest
from redis.exceptions import RedisError, ResponseError

from app.auth.revocation import (
    MAX_REVOCATION_TOMBSTONE_TTL_SECONDS,
    calculate_revocation_tombstone_ttl,
    get_revocation_redis_client,
    revoke_with_tombstone,
)


def test_calculate_revocation_tombstone_ttl_uses_safe_bounds() -> None:
    now = datetime(2026, 8, 17, tzinfo=UTC)

    assert calculate_revocation_tombstone_ttl(None, now=now) == (
        MAX_REVOCATION_TOMBSTONE_TTL_SECONDS
    )
    assert (
        calculate_revocation_tombstone_ttl(now + timedelta(seconds=90), now=now) == 90
    )
    assert (
        calculate_revocation_tombstone_ttl(now + timedelta(days=2), now=now)
        == MAX_REVOCATION_TOMBSTONE_TTL_SECONDS
    )
    assert calculate_revocation_tombstone_ttl(now - timedelta(seconds=1), now=now) == 1


def test_calculate_revocation_tombstone_ttl_accepts_naive_expiry() -> None:
    now = datetime(2026, 8, 17, tzinfo=UTC)
    naive_expiry = datetime(2026, 8, 17, 0, 2)

    assert calculate_revocation_tombstone_ttl(naive_expiry, now=now) == 120


def test_calculate_revocation_tombstone_ttl_accepts_naive_now() -> None:
    naive_now = datetime(2026, 8, 17)
    expires_at = datetime(2026, 8, 17, 0, 2, tzinfo=UTC)

    assert calculate_revocation_tombstone_ttl(expires_at, now=naive_now) == 120


@pytest.mark.asyncio
async def test_revoke_with_tombstone_uses_atomic_lua_path() -> None:
    client = AsyncMock()
    client.eval.return_value = 300

    ttl = await revoke_with_tombstone(
        client,
        session_key="session:jti-1",
        jti="jti-1",
        expires_at=None,
    )

    assert ttl == 300
    script, key_count, session_key, tombstone_key, fallback_ttl = (
        client.eval.await_args.args
    )
    assert key_count == 2
    assert session_key == "session:jti-1"
    assert tombstone_key == "revoked:jti:jti-1"
    assert fallback_ttl == MAX_REVOCATION_TOMBSTONE_TTL_SECONDS
    assert script.index("redis.call('SET'") < script.index("redis.call('DEL'")
    client.ttl.assert_not_awaited()
    client.set.assert_not_awaited()
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_with_tombstone_requires_a_security_client() -> None:
    with pytest.raises(RuntimeError, match="revocation Redis client is unavailable"):
        await revoke_with_tombstone(
            None,
            session_key="session:missing-client",
            jti="missing-client",
            expires_at=None,
        )


@pytest.mark.asyncio
async def test_get_revocation_redis_client_requires_configured_url() -> None:
    with patch(
        "app.core.config.settings",
        SimpleNamespace(revocation_redis_url="   "),
    ):
        with pytest.raises(
            RuntimeError, match="REVOCATION_REDIS_URL is not configured"
        ):
            await get_revocation_redis_client()


@pytest.mark.asyncio
async def test_get_revocation_redis_client_fails_closed_for_disabled_worker_role() -> (
    None
):
    with patch(
        "app.core.config.settings",
        SimpleNamespace(
            app_process_role="outbox-worker",
            revocation_redis_access_enabled=False,
            revocation_redis_url="redis://revocation.internal:6379/0",
        ),
    ):
        with pytest.raises(RuntimeError, match="disabled for this process role"):
            await get_revocation_redis_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_ttl", [0, -1, -2])
async def test_revoke_with_tombstone_fallback_covers_missing_or_unbounded_key(
    redis_ttl: int,
) -> None:
    client = AsyncMock()
    client.eval.side_effect = ResponseError("EVAL unavailable")
    client.ttl.return_value = redis_ttl
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    ttl = await revoke_with_tombstone(
        client,
        session_key="session:jti-2",
        jti="jti-2",
        expires_at=expires_at,
    )

    assert 295 <= ttl <= 300
    set_call = call.set("revoked:jti:jti-2", "1", ex=ttl)
    delete_call = call.delete("session:jti-2")
    assert set_call in client.mock_calls
    assert delete_call in client.mock_calls
    assert client.mock_calls.index(set_call) < client.mock_calls.index(delete_call)


@pytest.mark.asyncio
async def test_revoke_with_tombstone_fallback_preserves_positive_redis_ttl() -> None:
    client = AsyncMock()
    client.eval.side_effect = ResponseError("EVAL unavailable")
    client.ttl.return_value = 47

    ttl = await revoke_with_tombstone(
        client,
        session_key="session:jti-3",
        jti="jti-3",
        expires_at=None,
    )

    assert ttl == 47
    client.set.assert_awaited_once_with("revoked:jti:jti-3", "1", ex=47)
    client.delete.assert_awaited_once_with("session:jti-3")


@pytest.mark.asyncio
async def test_revoke_with_tombstone_does_not_delete_when_tombstone_write_fails() -> (
    None
):
    client = AsyncMock()
    client.eval.side_effect = ResponseError("EVAL unavailable")
    client.ttl.return_value = -2
    client.set.side_effect = RedisError("tombstone write failed")

    with pytest.raises(RedisError, match="tombstone write failed"):
        await revoke_with_tombstone(
            client,
            session_key="session:jti-4",
            jti="jti-4",
            expires_at=None,
        )

    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_with_tombstone_propagates_transport_failure() -> None:
    client = AsyncMock()
    client.eval.side_effect = RedisError("redis unavailable")

    with pytest.raises(RedisError, match="redis unavailable"):
        await revoke_with_tombstone(
            client,
            session_key="session:jti-5",
            jti="jti-5",
            expires_at=None,
        )

    client.ttl.assert_not_awaited()
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_with_tombstone_uses_dedicated_store_before_cache_delete() -> None:
    cache_client = AsyncMock()
    revocation_client = AsyncMock()
    order: list[str] = []

    async def _set(*_args, **_kwargs) -> None:
        order.append("tombstone")

    async def _delete(*_args, **_kwargs) -> None:
        order.append("cache-delete")

    revocation_client.set.side_effect = _set
    cache_client.delete.side_effect = _delete
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    ttl = await revoke_with_tombstone(
        cache_client,
        session_key="session:jti-dedicated",
        jti="jti-dedicated",
        expires_at=expires_at,
        revocation_redis_client=revocation_client,
    )

    assert 295 <= ttl <= 300
    revocation_client.set.assert_awaited_once_with(
        "revoked:jti:jti-dedicated", "1", ex=ttl
    )
    cache_client.delete.assert_awaited_once_with("session:jti-dedicated")
    cache_client.eval.assert_not_awaited()
    assert order == ["tombstone", "cache-delete"]
