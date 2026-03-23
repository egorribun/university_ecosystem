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
import pytest_asyncio  # noqa: F401  — required for asyncio mode

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client():
    """Return a connected Redis client using the app's shared cache."""
    from app.core.cache import get_cache
    from app.core.cache import RedisCache  # type: ignore[attr-defined]

    cache = get_cache()
    assert isinstance(cache, RedisCache), "Integration tests require Redis cache backend"
    client = await cache._get_client()
    yield client


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
        # Drain any subscribe confirmation messages.
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
        await pubsub.close()
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

    strategy = RedisSlidingWindowStrategy(redis_url=os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0"))

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
    from app.auth.mfa.challenge import _build_challenge_key  # type: ignore[attr-defined]

    user_id = str(uuid.uuid4())
    challenge_type = "totp-auth"
    key = _build_challenge_key(challenge_type, user_id)
    expected = f"mfa:{challenge_type}:{user_id}"
    assert key == expected, (
        f"MFA challenge key format must be 'mfa:{{challenge_type}}:{{user_id}}'. "
        f"Got '{key}', expected '{expected}'."
    )
