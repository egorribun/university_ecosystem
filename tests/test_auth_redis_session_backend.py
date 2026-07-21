"""Unit tests for the auth-layer Redis session backend (app/auth/redis_session.py).

NOTE: this is ``app.auth.redis_session.RedisSessionBackend`` — distinct from the
already-tested ``app.services.auth.redis_session.RedisSessionService`` (test_redis_sessions.py).

Hermetic via fakeredis. ``revoke_session`` first tries a Lua ``eval`` (which fakeredis
does not support and would raise an *uncaught* ResponseError), so the pipeline-fallback
branch is driven by a thin wrapper whose ``.eval`` raises ConnectionError (one of the
caught types) while delegating ttl/pipeline/delete/set/publish to a real FakeRedis.
The Lua happy-path is intentionally not unit-tested (no Lua under fakeredis).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from app.auth import redis_session as rs


class _EvalFailRedis:
    """Delegates to a real FakeRedis but forces the Lua ``eval`` to fail, so
    ``revoke_session`` takes the pipeline fallback (RZ-25-06)."""

    def __init__(self, inner: FakeRedis, *, publish_error: bool = False) -> None:
        self._inner = inner
        self._publish_error = publish_error

    async def eval(self, *_a, **_k):
        raise ConnectionError("Lua scripting unavailable")

    async def ttl(self, key):
        return await self._inner.ttl(key)

    def pipeline(self, transaction: bool = True):
        return self._inner.pipeline(transaction=transaction)

    async def delete(self, *keys):
        return await self._inner.delete(*keys)

    async def set(self, *a, **k):
        return await self._inner.set(*a, **k)

    async def get(self, key):
        return await self._inner.get(key)

    async def publish(self, channel, message):
        if self._publish_error:
            raise ConnectionError("pub/sub unavailable")
        return await self._inner.publish(channel, message)


# --------------------------------------------------------------------------- #
# register_session / is_session_valid
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_register_session_sets_key_with_positive_ttl():
    fake = FakeRedis(decode_responses=True)
    backend = rs.RedisSessionBackend(fake)
    jti = "jti-register"
    expires = datetime.now(UTC) + timedelta(seconds=120)

    await backend.register_session("user-1", jti, expires, metadata={"ip": "10.0.0.1"})

    raw = await fake.get(f"session:{jti}")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["user_id"] == "user-1"
    assert payload["ip"] == "10.0.0.1"
    assert await fake.ttl(f"session:{jti}") > 0


@pytest.mark.asyncio
async def test_register_session_skips_when_already_expired():
    fake = FakeRedis(decode_responses=True)
    backend = rs.RedisSessionBackend(fake)
    jti = "jti-expired"
    expires = datetime.now(UTC) - timedelta(seconds=5)  # ttl <= 0 → early return

    await backend.register_session("user-1", jti, expires)
    assert await fake.get(f"session:{jti}") is None


@pytest.mark.asyncio
async def test_is_session_valid_reflects_key_presence():
    fake = FakeRedis(decode_responses=True)
    backend = rs.RedisSessionBackend(fake)

    assert await backend.is_session_valid("absent") is False
    await fake.set("session:present", "1")
    assert await backend.is_session_valid("present") is True


# --------------------------------------------------------------------------- #
# revoke_session — pipeline fallback branches
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_revoke_session_pipeline_writes_tombstone_when_ttl_positive():
    inner = FakeRedis(decode_responses=True)
    jti = "jti-revoke"
    await inner.set(f"session:{jti}", "v", ex=100)  # ttl > 0
    backend = rs.RedisSessionBackend(_EvalFailRedis(inner))

    await backend.revoke_session(jti)

    assert await inner.get(f"session:{jti}") is None  # session deleted
    assert await inner.get(f"revoked:jti:{jti}") == "1"  # tombstone set


@pytest.mark.asyncio
async def test_revoke_session_deletes_without_tombstone_when_ttl_nonpositive():
    inner = FakeRedis(decode_responses=True)
    jti = "jti-revoke-no-ttl"  # key absent → ttl == -2
    backend = rs.RedisSessionBackend(_EvalFailRedis(inner))

    await backend.revoke_session(jti)

    assert await inner.get(f"revoked:jti:{jti}") is None  # ttl<=0 → no tombstone


@pytest.mark.asyncio
async def test_revoke_session_swallows_publish_failure():
    inner = FakeRedis(decode_responses=True)
    jti = "jti-publish-fail"
    await inner.set(f"session:{jti}", "v", ex=50)
    backend = rs.RedisSessionBackend(_EvalFailRedis(inner, publish_error=True))

    # publish raises ConnectionError → logged + swallowed, no propagation.
    await backend.revoke_session(jti)
    assert await inner.get(f"session:{jti}") is None


# --------------------------------------------------------------------------- #
# get_session_backend factory
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_session_backend_returns_redis_backend_when_available(monkeypatch):
    fake_client = FakeRedis(decode_responses=True)
    cache = MagicMock(spec=rs.RedisCache)
    cache._get_client = AsyncMock(return_value=fake_client)
    monkeypatch.setattr(rs, "get_cache", lambda: cache)
    monkeypatch.setattr(rs.settings, "session_storage_backend", "redis")

    backend = await rs.get_session_backend()
    assert isinstance(backend, rs.RedisSessionBackend)


@pytest.mark.asyncio
async def test_get_session_backend_non_redis_backend_returns_null(monkeypatch):
    monkeypatch.setattr(rs.settings, "session_storage_backend", "memory")

    backend = await rs.get_session_backend()
    # NullSessionBackend: revocation disabled — always valid + warn-once.
    assert await backend.is_session_valid("a") is True  # first call warns
    assert await backend.is_session_valid("b") is True  # second skips the warn branch
    await backend.register_session("u", "j", datetime.now(UTC))  # no-op
    await backend.revoke_session("j")  # no-op


@pytest.mark.asyncio
async def test_get_session_backend_redis_unavailable_in_prod_raises(monkeypatch):
    monkeypatch.setattr(rs.settings, "session_storage_backend", "redis")
    monkeypatch.setattr(rs, "get_cache", lambda: MagicMock())  # NOT a RedisCache
    monkeypatch.setattr(rs.settings, "environment", "production")

    with pytest.raises(RuntimeError, match="refusing to start"):
        await rs.get_session_backend()


@pytest.mark.asyncio
async def test_get_session_backend_redis_unavailable_in_testing_falls_through(
    monkeypatch,
):
    monkeypatch.setattr(rs.settings, "session_storage_backend", "redis")
    monkeypatch.setattr(rs, "get_cache", lambda: MagicMock())  # NOT a RedisCache
    monkeypatch.setattr(rs.settings, "environment", "testing")

    backend = await rs.get_session_backend()  # dev/test env → no raise
    assert await backend.is_session_valid("any") is True


@pytest.mark.asyncio
async def test_session_backend_abstract_methods() -> None:
    # Coverage for pass statements in SessionBackend abstract base class
    class DummyBackend(rs.SessionBackend):
        async def register_session(self, user_id, jti, expires_at, metadata=None):
            await super().register_session(user_id, jti, expires_at, metadata)

        async def is_session_valid(self, jti):
            return await super().is_session_valid(jti)

        async def revoke_session(self, jti):
            await super().revoke_session(jti)

    dummy = DummyBackend()
    await dummy.register_session("user-1", "jti", datetime.now(UTC))
    assert await dummy.is_session_valid("jti") is None
    await dummy.revoke_session("jti")


@pytest.mark.asyncio
async def test_revoke_session_unexpected_error() -> None:
    # Test line 99: unexpected error in eval (e.g. ValueError) is re-raised
    mock_client = AsyncMock()
    mock_client.eval = AsyncMock(side_effect=ValueError("unexpected"))
    backend = rs.RedisSessionBackend(mock_client)

    with pytest.raises(ValueError, match="unexpected"):
        await backend.revoke_session("jti")
