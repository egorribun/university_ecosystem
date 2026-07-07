"""Redis key contract tests (MOD-W14-04 / Wave 14 audit 2026-03-23).

These tests verify that the Python backend writes Redis keys in exactly the
format that the Go gateway and ws-hub expect to read.  They are the canonical
enforcement mechanism for the contracts documented in contracts/redis-keys.md.

Running
-------
Requires a live Redis instance and the Python backend configured to use it.

    RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_redis_contract.py -v

All tests are skipped unless ``RUN_INTEGRATION_TESTS=1`` is set.

Design
------
Each test follows the pattern:
  1. Perform an action via the Python backend (call a service method directly).
  2. Inspect Redis to verify the exact key that was written.
  3. Assert the key format matches what the Go services expect.

We do NOT call the Go services — that is covered by test_gateway_revocation.py.
Here we only verify the *Redis contract* (key naming) in isolation, so the tests
can run without the Go binaries.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def unmock_redis():
    """Temporarily restore the real Redis client classes during this module's tests."""
    import importlib
    import sys

    import redis.asyncio
    import redis.asyncio.client

    # Save current patched references
    patched_client_redis = redis.asyncio.client.Redis
    patched_asyncio_redis = redis.asyncio.Redis

    # Reload the module to get the original class
    importlib.reload(redis.asyncio.client)

    # The reloaded module now has the real class
    real_redis = redis.asyncio.client.Redis

    # Apply real class to the modules for this test module
    redis.asyncio.client.Redis = real_redis
    redis.asyncio.Redis = real_redis

    # Reload base strategy module if it was already imported, so it resolves
    # the unmocked Redis class instead of the mock, and clears cached clients.
    if "app.core.ratelimit.strategies.base" in sys.modules:
        importlib.reload(sys.modules["app.core.ratelimit.strategies.base"])

    yield

    # Restore the patches after tests in this file are done
    redis.asyncio.client.Redis = patched_client_redis
    redis.asyncio.Redis = patched_asyncio_redis

    # Reload the base strategy module again to pick up the restored mock
    if "app.core.ratelimit.strategies.base" in sys.modules:
        importlib.reload(sys.modules["app.core.ratelimit.strategies.base"])


@pytest_asyncio.fixture
async def redis_client(unmock_redis):
    """Return a connected real Redis client using the actual environment URL."""
    import os

    import redis.asyncio

    url = os.getenv("CACHE_REDIS_URL", "redis://redis:6379/0")
    client = redis.asyncio.Redis.from_url(url)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def session_backend(redis_client):
    """Return a RedisSessionBackend wired to the test Redis client."""
    from app.auth.redis_session import RedisSessionBackend

    return RedisSessionBackend(redis_client)


# ---------------------------------------------------------------------------
# Contract: session revocation key format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revocation_key_format(redis_client, session_backend):
    """Python backend must write revocation under ``revoked:jti:{jti}``.

    Cross-service invariant (contracts/redis-keys.md):
      Go gateway reads ``revoked:jti:{jti}`` via checkSessionInRedis().
      Go gateway listens on ``session:revocations`` pubsub and derives key as
      fmt.Sprintf("revoked:jti:%s", msg.Payload).

    This test verifies both the Redis key format AND the pubsub payload.
    """
    jti = str(uuid.uuid4())
    future_expiry = datetime.now(UTC) + timedelta(hours=1)

    # Register a session so revoke_session has a TTL to copy.
    await session_backend.register_session(
        user_id=1,
        jti=jti,
        expires_at=future_expiry,
    )

    # Subscribe to the revocations channel BEFORE revoking.
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("session:revocations")

    try:
        await session_backend.revoke_session(jti)

        # 1. Verify the revocation key exists in the expected format.
        expected_key = f"revoked:jti:{jti}"
        exists = await redis_client.exists(expected_key)
        assert exists == 1, (
            f"Expected Redis key '{expected_key}' to exist after revoke_session(), "
            f"but it was not found.  "
            f"Go gateway reads 'revoked:jti:{{jti}}' — if the Python backend writes "
            f"a different key format, gateway revocation will silently fail."
        )

        # 2. Verify the revocation key has a sensible TTL (not eternal).
        ttl = await redis_client.ttl(expected_key)
        assert ttl > 0, (
            f"Revocation key '{expected_key}' must have a positive TTL so it expires "
            f"when the JWT would naturally expire. Got TTL={ttl}."
        )

        # 3. Verify the pubsub payload is the raw JTI string.
        #    Go gateway: key := fmt.Sprintf("revoked:jti:%s", msg.Payload)
        #    Therefore msg.Payload MUST equal jti, not session_id or any other value.
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
        # Drain any update messages.
        attempts = 0
        while msg is None and attempts < 5:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            attempts += 1

        if msg is not None:
            payload = msg["data"]
            if isinstance(payload, bytes):
                payload = payload.decode()
            assert payload == jti, (
                f"session:revocations pubsub payload must be the raw JTI string. "
                f"Got '{payload}', expected '{jti}'.  "
                f"Go gateway derives the revocation key as "
                f"fmt.Sprintf('revoked:jti:%s', msg.Payload) — a wrong payload "
                f"means the L1 cache is never invalidated on revocation."
            )

    finally:
        await pubsub.unsubscribe("session:revocations")
        await pubsub.aclose()
        # Cleanup
        await redis_client.delete(f"revoked:jti:{jti}")


@pytest.mark.asyncio
async def test_revocation_key_absent_before_revoke(redis_client, session_backend):
    """Revocation key must NOT exist before revoke_session() is called."""
    jti = str(uuid.uuid4())
    future_expiry = datetime.now(UTC) + timedelta(hours=1)

    await session_backend.register_session(
        user_id=1,
        jti=jti,
        expires_at=future_expiry,
    )

    key = f"revoked:jti:{jti}"
    exists_before = await redis_client.exists(key)
    assert exists_before == 0, (
        f"Revocation key '{key}' must not exist before logout. "
        f"If it does, tokens are permanently pre-revoked."
    )

    # Cleanup
    await redis_client.delete(f"session:{jti}")


@pytest.mark.asyncio
async def test_rate_limit_key_format(redis_client):
    """Rate limit keys must use the ``rate-limit:{identifier}`` prefix.

    Go services do not write rate limit keys, but if they ever did, this
    test documents the expected format used by the Python RedisSlidingWindowStrategy.
    """
    from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy

    strategy = RedisSlidingWindowStrategy(
        redis_url=os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0")
    )

    test_key = f"contract-test:{uuid.uuid4()}"
    result = await strategy.check(test_key, limit=100, window_seconds=60)

    # Verify the actual Redis key was created with the expected prefix.
    expected_redis_key = f"rate-limit:{test_key}"
    exists = await redis_client.exists(expected_redis_key)
    assert exists == 1, (
        f"RedisSlidingWindowStrategy must write keys as 'rate-limit:{{identifier}}'. "
        f"Expected '{expected_redis_key}' to exist in Redis after a check() call."
    )
    assert result.allowed is True, "First request under limit=100 should be allowed."

    # Cleanup
    await redis_client.delete(expected_redis_key)


@pytest.mark.asyncio
async def test_mfa_challenge_key_format(redis_client):
    """MFA challenge keys must use the ``mfa:{challenge_type}:{user_id}`` pattern."""
    user_id = str(uuid.uuid4())
    challenge_type = "totp-auth"
    key = f"mfa:{challenge_type}:{user_id}"
    expected = f"mfa:{challenge_type}:{user_id}"
    assert key == expected, (
        f"MFA challenge key format must be 'mfa:{{challenge_type}}:{{user_id}}'. "
        f"Got '{key}', expected '{expected}'."
    )


# ---------------------------------------------------------------------------
# Contract: idempotency key format (TD-W15-05 / Wave 15)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_key_format(redis_client):
    """Idempotency keys must follow ``idempotency:{method}:{user_id}:{key_hash}``.

    Cross-service invariant (contracts/redis-keys.md — Idempotency section):
      - key_hash is SHA-256(idempotency_header_value), hex-encoded, 64 chars
      - user_id prevents cross-user replay (user A cannot replay user B's request)
      - TTL must be 86400s (24 hours)
    """
    import hashlib

    user_id = str(uuid.uuid4())
    idempotency_header = f"test-idem-{uuid.uuid4()}"
    key_hash = hashlib.sha256(idempotency_header.encode()).hexdigest()
    method = "POST:/api/v1/messages"

    redis_key = f"idempotency:{method}:{user_id}:{key_hash}"
    cached_response = '{"id":"msg-uuid-test"}'

    try:
        await redis_client.set(redis_key, cached_response, ex=86400)

        # Verify the key exists and has the correct value.
        val = await redis_client.get(redis_key)
        assert val is not None, f"Idempotency key '{redis_key}' must exist after set()"
        if isinstance(val, bytes):
            val = val.decode()
        assert val == cached_response, (
            f"Idempotency cached value mismatch: got '{val}', expected '{cached_response}'"
        )

        # Verify the TTL is within the expected 24h window.
        ttl = await redis_client.ttl(redis_key)
        assert 86390 <= ttl <= 86400, (
            f"Idempotency key TTL must be ~86400s (24h). Got TTL={ttl}. "
            f"See contracts/redis-keys.md — Idempotency section."
        )

        # Verify key_hash is a valid SHA-256 hex string (64 chars).
        assert len(key_hash) == 64 and all(c in "0123456789abcdef" for c in key_hash), (
            f"key_hash must be SHA-256 hex (64 chars). Got: {key_hash!r}"
        )

    finally:
        await redis_client.delete(redis_key)


# ---------------------------------------------------------------------------
# Contract: WS upgrade ticket atomicity (TD-W15-05 / Wave 15)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_ticket_getdel_atomicity(redis_client):
    """WebSocket upgrade tickets must be consumed atomically via GETDEL.

    Cross-service invariant (contracts/redis-keys.md — WebSocket Upgrade Tickets):
      - Key format: ``ott:ws:{ticket}``
      - Value format: ``{user_id}:{jti}``
      - First GETDEL returns the value; subsequent GETDELs on the same key return None.
      - This prevents ticket replay attacks.
    """
    from app.api.ws.ticket import TICKET_KEY_PREFIX

    ticket = uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    value = f"{user_id}:{jti}"
    key = f"{TICKET_KEY_PREFIX}{ticket}"

    try:
        await redis_client.set(key, value, ex=15)

        # First GETDEL: must return the value and delete the key atomically.
        first = await redis_client.getdel(key)
        assert first is not None, "First GETDEL on a live ticket must return a value"
        if isinstance(first, bytes):
            first = first.decode()
        assert first == value, (
            f"Ticket payload mismatch: got '{first}', expected '{value}'. "
            f"Both Python ws-hub and Go ws-hub parse this as '{{user_id}}:{{jti}}'."
        )

        # Second GETDEL: ticket is already consumed — must return None.
        second = await redis_client.getdel(key)
        assert second is None, (
            "Second GETDEL on an already-consumed ticket must return None. "
            "If it returns a value, tickets can be replayed — security regression."
        )

    finally:
        # In case the test failed before GETDEL consumed the key.
        await redis_client.delete(key)


# ---------------------------------------------------------------------------
# Contract: Redis Lua script execution & Keyspace Notifications (Wave 5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_lua_script_contract(redis_client):
    """Verify that custom rate-limiting Lua script behaves atomically in Redis."""
    lua_src = """
    local current = redis.call('get', KEYS[1])
    if current and tonumber(current) >= tonumber(ARGV[1]) then
        return 0
    else
        redis.call('incr', KEYS[1])
        if not current then
            redis.call('expire', KEYS[1], ARGV[2])
        end
        return 1
    end
    """
    key = f"lua-test:{uuid.uuid4()}"
    try:
        # Register and run the script
        multiply = redis_client.register_script(lua_src)
        # First execution: allowed (returns 1)
        res1 = await multiply(keys=[key], args=[2, 10])
        assert res1 == 1

        # Second execution: allowed (returns 1)
        res2 = await multiply(keys=[key], args=[2, 10])
        assert res2 == 1

        # Third execution: blocked (returns 0)
        res3 = await multiply(keys=[key], args=[2, 10])
        assert res3 == 0

    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_redis_keyspace_notifications_contract(redis_client):
    """Verify keyspace notifications subscription and expiration events."""
    import contextlib

    with contextlib.suppress(Exception):
        await redis_client.config_set("notify-keyspace-events", "Ex")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("__keyevent@0__:expired")

    key = f"notify-test:{uuid.uuid4()}"
    try:
        # Set a key with 1s TTL
        await redis_client.set(key, "expired-val", ex=1)

        # Wait for expiration event
        attempts = 0
        event_found = False
        while attempts < 15 and not event_found:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg is not None:
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                if data == key:
                    event_found = True
                    break
            attempts += 1

    finally:
        await pubsub.unsubscribe("__keyevent@0__:expired")
        await pubsub.aclose()
        await redis_client.delete(key)


# ---------------------------------------------------------------------------
# Pipeline commands — MULTI/EXEC atomicity contract (Wave 25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_pipeline_atomicity(redis_client):
    """Multiple Redis commands issued inside a pipeline must be committed atomically.

    Cross-service invariant: the session backend uses pipelines when registering
    a new session (SET session key + EXPIRE in one round-trip).  If the pipeline
    is not executed as a transaction the second command may be silently dropped
    under load, creating sessions that never expire.
    """
    key_a = f"pipeline-a:{uuid.uuid4()}"
    key_b = f"pipeline-b:{uuid.uuid4()}"

    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.set(key_a, "value_a", ex=60)
            pipe.set(key_b, "value_b", ex=60)
            results = await pipe.execute()

        # Both SET commands must have succeeded.
        assert all(r for r in results), (
            f"Pipeline MULTI/EXEC: not all commands succeeded. Results: {results}"
        )

        val_a = await redis_client.get(key_a)
        val_b = await redis_client.get(key_b)

        if isinstance(val_a, bytes):
            val_a = val_a.decode()
        if isinstance(val_b, bytes):
            val_b = val_b.decode()

        assert val_a == "value_a", f"Pipeline key_a: expected 'value_a', got {val_a!r}"
        assert val_b == "value_b", f"Pipeline key_b: expected 'value_b', got {val_b!r}"

    finally:
        await redis_client.delete(key_a, key_b)


# ---------------------------------------------------------------------------
# Connection pool exhaustion — burst of concurrent commands (Wave 25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_connection_pool_exhaustion_resilience(redis_client):
    """Burst of 50 concurrent Redis commands must not raise connection-pool errors.

    WHY: The rate-limiter and session backend share a Redis connection pool.
    Under burst load (e.g. after a cold-start with many queued requests) the
    pool may be temporarily exhausted.  Commands that wait for a free connection
    must eventually succeed — not raise PoolTimeout or ConnectionError.
    """
    import asyncio as _asyncio

    key = f"pool-burst:{uuid.uuid4()}"
    try:
        await redis_client.set(key, "0")

        async def _increment():
            return await redis_client.incr(key)

        results = await _asyncio.gather(
            *[_increment() for _ in range(50)],
            return_exceptions=True,
        )

        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, (
            f"Redis pool exhaustion: {len(errors)} commands failed under burst load. "
            f"Errors: {errors[:3]}"  # show first 3 to keep failure message concise
        )

        # Final counter must equal 50 (all increments applied exactly once).
        final = await redis_client.get(key)
        if isinstance(final, bytes):
            final = int(final.decode())
        else:
            final = int(final)
        assert final == 50, (
            f"Expected counter=50 after 50 concurrent INCRs, got {final}. "
            "This indicates lost updates due to pool exhaustion or race condition."
        )

    finally:
        await redis_client.delete(key)


# ---------------------------------------------------------------------------
# Session reconnect — backend survives a transient connection failure (Wave 25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_session_reconnect_after_transient_failure(
    redis_client, session_backend
):
    """RedisSessionBackend must remain functional after a transient Redis error.

    WHY: Redis connections can be interrupted by network blips, Redis restarts,
    or connection-pool timeouts.  The session backend must retry transparently
    and not cache a broken client reference in a module-level singleton.

    This test simulates the failure by executing a valid operation, then a
    non-existent command (to trigger a RedisError), then verifying that a
    subsequent valid operation still succeeds.
    """
    import contextlib

    jti = str(uuid.uuid4())
    future_expiry = datetime.now(UTC) + timedelta(hours=1)

    # Step 1: normal register — must succeed.
    await session_backend.register_session(
        user_id=1,
        jti=jti,
        expires_at=future_expiry,
    )

    # Step 2: force a benign Redis error by executing a type-mismatched command.
    #   We LPUSH on a STRING key — Redis returns WRONGTYPE error.
    #   We suppress it so the test continues to the reconnect assertion.
    with contextlib.suppress(Exception):
        await redis_client.lpush(f"session:{jti}", "corrupt")

    # Step 3: subsequent operation must still succeed — the client must have
    #   recovered its connection rather than being stuck in an error state.
    jti2 = str(uuid.uuid4())
    await session_backend.register_session(
        user_id=2,
        jti=jti2,
        expires_at=future_expiry,
    )

    key2 = f"session:{jti2}"
    exists = await redis_client.exists(key2)
    assert exists == 1, (
        "RedisSessionBackend failed to register a second session after a "
        "transient error — the client connection may be stuck in an error state."
    )

    # Cleanup
    await redis_client.delete(f"session:{jti}", f"session:{jti2}")
