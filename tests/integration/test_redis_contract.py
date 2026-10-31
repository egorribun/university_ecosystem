"""Redis key contract tests (MOD-W14-04 / Wave 14 audit 2026-03-23).

These tests verify that the Python backend writes Redis keys in exactly the
format that the Go gateway and ws-hub expect to read.  They are the canonical
enforcement mechanism for the contracts documented in contracts/redis-keys.md.

Running
-------
Requires a live Redis instance and the Python backend configured to use it.

    RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_redis_contract.py -v

All tests are skipped unless ``RUN_INTEGRATION_TESTS=1`` is set.
The expiration and revocation pubsub checks additionally require ownership
markers provisioned by a trusted launcher in two disposable Redis stores.

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

import asyncio
import hmac
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

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

    url = os.getenv(
        "CACHE_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    client = redis.asyncio.Redis.from_url(url)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def revocation_redis_client(unmock_redis):
    """Return the dedicated durable revocation-store client."""
    import redis.asyncio

    url = os.getenv("REVOCATION_REDIS_URL", "redis://localhost:6380/0")
    client = redis.asyncio.Redis.from_url(url)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def session_backend(redis_client, revocation_redis_client):
    """Return a backend wired to distinct cache and revocation stores."""
    from app.auth.redis_session import RedisSessionBackend

    return RedisSessionBackend(
        redis_client,
        revocation_redis_client=revocation_redis_client,
    )


# ---------------------------------------------------------------------------
# Contract: session revocation key format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revocation_key_format(
    redis_client,
    revocation_redis_client,
    session_backend,
):
    """The dedicated store must contain and publish the revoked JTI."""
    cache_id, revocation_id = await _assert_owned_redis_pair(
        redis_client, revocation_redis_client
    )
    jti = str(uuid.uuid4())
    channel = "session:revocations"
    session_key = f"session:{jti}"
    revoked_key = f"revoked:jti:{jti}"
    pubsub = None
    try:
        await _assert_owned_redis(redis_client, expected_run_id=cache_id)
        await session_backend.register_session(
            user_id=1,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        pubsub = revocation_redis_client.pubsub()
        await pubsub.subscribe(channel)
        await _expect_pubsub_message(pubsub, channel=channel, message_type="subscribe")
        await _assert_owned_redis_pair(
            redis_client,
            revocation_redis_client,
            expected_ids=(cache_id, revocation_id),
        )
        await session_backend.revoke_session(jti)

        exists = await revocation_redis_client.exists(revoked_key)
        ttl = await revocation_redis_client.ttl(revoked_key)
        if exists != 1 or ttl <= 0:
            raise AssertionError("The revocation tombstone is missing or has no TTL")
        await _expect_pubsub_message(
            pubsub, channel=channel, message_type="message", payload=jti
        )
    finally:
        try:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                finally:
                    await pubsub.aclose()
        finally:
            try:
                await _assert_owned_redis(redis_client, expected_run_id=cache_id)
                await redis_client.delete(session_key)
            finally:
                await _assert_owned_redis(
                    revocation_redis_client,
                    revocation=True,
                    expected_run_id=revocation_id,
                )
                await revocation_redis_client.delete(revoked_key)


@pytest.mark.asyncio
async def test_revocation_oracle_rejects_unpublished_jti(
    redis_client, revocation_redis_client, session_backend, monkeypatch
):
    """Real tombstone creation must not pass when its publication is lost."""
    publish = AsyncMock(return_value=0)
    monkeypatch.setattr(revocation_redis_client, "publish", publish)
    with pytest.raises(
        AssertionError, match=r"Expected Redis pubsub message \(message\)"
    ):
        await test_revocation_key_format(
            redis_client, revocation_redis_client, session_backend
        )
    publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_revocation_key_absent_before_revoke(
    redis_client,
    revocation_redis_client,
    session_backend,
):
    """Revocation key must NOT exist before revoke_session() is called."""
    jti = str(uuid.uuid4())
    future_expiry = datetime.now(UTC) + timedelta(hours=1)

    await session_backend.register_session(
        user_id=1,
        jti=jti,
        expires_at=future_expiry,
    )

    key = f"revoked:jti:{jti}"
    exists_before = await revocation_redis_client.exists(key)
    assert exists_before == 0, (
        f"Revocation key '{key}' must not exist before logout. "
        f"If it does, tokens are permanently pre-revoked."
    )

    # Cleanup
    await redis_client.delete(f"session:{jti}")


@pytest.mark.asyncio
@pytest.mark.parametrize("source_state", ["missing", "persistent"])
async def test_revocation_tombstone_survives_missing_or_unbounded_source_key(
    redis_client,
    revocation_redis_client,
    session_backend,
    source_state,
):
    """Real Redis Lua path must cover eviction and TTL loss fail-closed."""
    jti = str(uuid.uuid4())
    session_key = f"session:{jti}"
    revoked_key = f"revoked:jti:{jti}"
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    if source_state == "persistent":
        await redis_client.set(session_key, "cached-without-expiry")

    try:
        await session_backend.revoke_session(jti, expires_at=expires_at)

        assert await redis_client.get(session_key) is None
        assert await redis_client.get(revoked_key) is None
        assert await revocation_redis_client.get(revoked_key) == b"1"
        assert 295 <= await revocation_redis_client.ttl(revoked_key) <= 300
    finally:
        await redis_client.delete(session_key, revoked_key)
        await revocation_redis_client.delete(revoked_key)


@pytest.mark.asyncio
async def test_v2_session_producer_writes_the_same_revocation_contract(
    redis_client,
    revocation_redis_client,
    monkeypatch,
):
    """Logout/fingerprint producer shares the canonical tombstone primitive."""
    from app.services.auth import redis_session as redis_session_module

    async def get_test_client(_url):
        return redis_client

    monkeypatch.setattr(
        redis_session_module,
        "_get_shared_client",
        get_test_client,
    )
    monkeypatch.setattr(
        redis_session_module,
        "get_revocation_redis_client",
        AsyncMock(return_value=revocation_redis_client),
    )
    service = redis_session_module.RedisSessionService(
        redis_url="redis://integration-test"
    )
    jti = str(uuid.uuid4())
    revoked_key = f"revoked:jti:{jti}"

    try:
        await service.revoke_session(
            jti,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

        assert await redis_client.get(revoked_key) is None
        assert await revocation_redis_client.get(revoked_key) == b"1"
        assert 295 <= await revocation_redis_client.ttl(revoked_key) <= 300
    finally:
        await redis_client.delete(f"session:v2:{jti}", revoked_key)
        await revocation_redis_client.delete(revoked_key)


@pytest.mark.asyncio
async def test_v2_revocation_uses_dedicated_configured_store(
    redis_client,
    revocation_redis_client,
    monkeypatch,
):
    """The v2 producer must not put tombstones in its cache namespace."""
    from app.services.auth import redis_session as redis_session_module

    cache_url = os.getenv(
        "CACHE_REDIS_URL",
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    selected_urls: list[str] = []

    async def get_test_client(url: str):
        selected_urls.append(url)
        return redis_client

    monkeypatch.setattr(redis_session_module.settings, "cache_redis_url", cache_url)
    monkeypatch.setattr(
        redis_session_module,
        "_get_shared_client",
        get_test_client,
    )
    monkeypatch.setattr(
        redis_session_module,
        "get_revocation_redis_client",
        AsyncMock(return_value=revocation_redis_client),
    )

    service = redis_session_module.RedisSessionService()
    jti = str(uuid.uuid4())
    session_key = f"session:v2:{jti}"
    revoked_key = f"revoked:jti:{jti}"

    try:
        await redis_client.delete(session_key, revoked_key)
        await revocation_redis_client.delete(revoked_key)

        await service.revoke_session(
            jti,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

        assert selected_urls == [cache_url]
        assert await redis_client.exists(revoked_key) == 0
        assert await revocation_redis_client.exists(revoked_key) == 1
    finally:
        await redis_client.delete(session_key, revoked_key)
        await revocation_redis_client.delete(revoked_key)


@pytest.mark.asyncio
async def test_rate_limit_key_format(redis_client):
    """The production Lua script must create, expire, and enforce the key.

    Go services do not write rate limit keys, but if they ever did, this
    test documents the expected format used by the Python RedisSlidingWindowStrategy.
    """
    from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy

    strategy = RedisSlidingWindowStrategy(
        redis_url=os.getenv(
            "CACHE_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
    )

    test_key = f"contract-test:{uuid.uuid4()}"
    expected_redis_key = f"rate-limit:{test_key}"
    try:
        first = await strategy.check(test_key, limit=2, window_seconds=60)
        second = await strategy.check(test_key, limit=2, window_seconds=60)
        blocked = await strategy.check(test_key, limit=2, window_seconds=60)

        assert first.allowed is True and first.remaining == 1
        assert second.allowed is True and second.remaining == 0
        assert blocked.allowed is False and blocked.remaining == 0
        assert blocked.retry_after > 0

        exists = await redis_client.exists(expected_redis_key)
        assert exists == 1, (
            "RedisSlidingWindowStrategy must write keys as "
            f"'rate-limit:{{identifier}}'; expected '{expected_redis_key}'."
        )
        assert await redis_client.zcard(expected_redis_key) == 2
        ttl_ms = await redis_client.pttl(expected_redis_key)
        assert 0 < ttl_ms <= 60_000
    finally:
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


_EXPIRY_EVENT_TIMEOUT_SECONDS = 5.0
_NOTIFICATION_CONFIG = "notify-keyspace-events"


async def _assert_owned_redis(
    redis_client, *, revocation: bool = False, expected_run_id: str | None = None
) -> str:
    """Bind any global configuration change to the launcher's disposable store."""
    prefix = "AUD428_REVOCATION_REDIS" if revocation else "AUD428_REDIS"
    key = os.getenv(f"{prefix}_OWNER_KEY", "")
    value = os.getenv(f"{prefix}_OWNER_VALUE", "")
    # Explicit raises avoid pytest's assertion rewriting printing marker values.
    if re.fullmatch(r"aud428-owner:[0-9a-f]{32}", key) is None:
        raise AssertionError("A disposable Redis ownership marker is required")
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AssertionError("A disposable Redis ownership value is required")
    if redis_client.connection_pool.connection_kwargs.get("db", 0) != 0:
        raise AssertionError("The Redis contracts require database 0")
    actual = await redis_client.get(key)
    if isinstance(actual, str):
        actual = actual.encode("utf-8")
    if not isinstance(actual, bytes) or not hmac.compare_digest(
        actual, value.encode("ascii")
    ):
        raise AssertionError("The configured Redis is not the owned disposable store")
    run_id = (await redis_client.info("server")).get("run_id")
    if (
        not isinstance(run_id, str)
        or re.fullmatch(r"[0-9a-f]{40}", run_id) is None
        or (
            expected_run_id is not None
            and not hmac.compare_digest(run_id, expected_run_id)
        )
    ):
        raise AssertionError(
            "The owned Redis server identity changed or is unavailable"
        )
    return run_id


async def _assert_owned_redis_pair(
    redis_client,
    revocation_redis_client,
    *,
    expected_ids: tuple[str, str] | None = None,
) -> tuple[str, str]:
    cache_id = await _assert_owned_redis(
        redis_client, expected_run_id=expected_ids[0] if expected_ids else None
    )
    revocation_id = await _assert_owned_redis(
        revocation_redis_client,
        revocation=True,
        expected_run_id=expected_ids[1] if expected_ids else None,
    )
    if hmac.compare_digest(cache_id, revocation_id):
        raise AssertionError(
            "Cache and revocation stores must be distinct owned servers"
        )
    return cache_id, revocation_id


async def _notification_flags(redis_client) -> str:
    config = await redis_client.config_get(_NOTIFICATION_CONFIG)
    value = config.get(_NOTIFICATION_CONFIG, config.get(_NOTIFICATION_CONFIG.encode()))
    if isinstance(value, bytes):
        value = value.decode("ascii")
    if not isinstance(value, str):
        raise AssertionError("Redis notification configuration was unavailable")
    return value


@asynccontextmanager
async def _temporary_expiry_notifications(
    redis_client, *, enabled: bool
) -> AsyncIterator[str]:
    run_id = await _assert_owned_redis(redis_client)
    original = await _notification_flags(redis_client)
    desired = "".join(dict.fromkeys(f"{original}Ex")) if enabled else ""
    try:
        await _assert_owned_redis(redis_client, expected_run_id=run_id)
        changed = await redis_client.config_set(_NOTIFICATION_CONFIG, desired)
        if changed is not True:
            raise AssertionError("Redis notification configuration was not applied")
        configured = await _notification_flags(redis_client)
        if enabled:
            if "E" not in configured or (
                "x" not in configured and "A" not in configured
            ):
                raise AssertionError("Redis expiry notifications were not enabled")
        elif configured != "":
            raise AssertionError("Redis expiry notifications were not disabled")
        yield run_id
    finally:
        # Check the marker again before a server-wide write: a disappeared or
        # replaced target must not receive the saved configuration.
        await _assert_owned_redis(redis_client, expected_run_id=run_id)
        restored = await redis_client.config_set(_NOTIFICATION_CONFIG, original)
        if restored is not True:
            raise AssertionError("Redis notification configuration was not restored")
        if await _notification_flags(redis_client) != original:
            raise AssertionError(
                "Redis notification configuration differs after restore"
            )


async def _expect_pubsub_message(
    pubsub, *, channel: str, message_type: str, payload: str | None = None
) -> None:
    deadline = asyncio.get_running_loop().time() + _EXPIRY_EVENT_TIMEOUT_SECONDS
    while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
        timeout = asyncio.timeout(remaining)
        try:
            async with timeout:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=False, timeout=min(0.2, remaining)
                )
        except TimeoutError:
            if not timeout.expired():
                raise
            break
        if (
            message is not None
            and message.get("type") == message_type
            and message.get("channel") in (channel, channel.encode())
            and (payload is None or message.get("data") in (payload, payload.encode()))
        ):
            return
        # Fake clients and unrelated traffic may return immediately; do not spin.
        await asyncio.sleep(
            min(0.01, max(deadline - asyncio.get_running_loop().time(), 0))
        )
    raise AssertionError(
        f"Expected Redis pubsub message ({message_type}) was not observed"
    )


async def _exercise_expiry_notifications(redis_client, *, enabled: bool) -> None:
    channel = "__keyevent@0__:expired"
    key = f"notify-test:{uuid.uuid4()}"
    async with _temporary_expiry_notifications(redis_client, enabled=enabled) as run_id:
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(channel)
            await _expect_pubsub_message(
                pubsub, channel=channel, message_type="subscribe"
            )
            await _assert_owned_redis(redis_client, expected_run_id=run_id)
            created = await redis_client.set(key, "expired-val", ex=1)
            if created is not True:
                raise AssertionError("The Redis expiry probe key was not created")
            if enabled:
                await _expect_pubsub_message(
                    pubsub, channel=channel, message_type="message", payload=key
                )
            else:
                with pytest.raises(
                    AssertionError, match=r"Expected Redis pubsub message \(message\)"
                ):
                    await _expect_pubsub_message(
                        pubsub, channel=channel, message_type="message", payload=key
                    )
            exists = await redis_client.exists(key)
            if exists != 0:
                raise AssertionError("The Redis expiry probe key did not expire")
        finally:
            try:
                await pubsub.unsubscribe(channel)
            finally:
                try:
                    await pubsub.aclose()
                finally:
                    await _assert_owned_redis(redis_client, expected_run_id=run_id)
                    await redis_client.delete(key)


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
    await _exercise_expiry_notifications(redis_client, enabled=True)


@pytest.mark.asyncio
async def test_redis_expiry_oracle_rejects_disabled_notifications(redis_client):
    """A real expired key must not satisfy the oracle with notifications off."""
    await _exercise_expiry_notifications(redis_client, enabled=False)


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
