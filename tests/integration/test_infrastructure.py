import os

import nats
import psycopg
import pytest

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
pytestmark = pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run")


@pytest.fixture(scope="module")
def postgres():
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:15-alpine@sha256:fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b"
    ) as postgres:
        yield postgres


@pytest.fixture(scope="module")
def redis_client():
    # Import lazily so disabled integration tests do not load Docker dependencies.
    from testcontainers.community.redis import RedisContainer

    with RedisContainer(
        "redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
    ) as redis:
        yield redis


@pytest.fixture(scope="module")
def nats_server():
    from testcontainers.core.container import DockerContainer

    with DockerContainer(
        "nats:2.15.0-alpine@sha256:ac8f88a6494bffc2c2a5289a0ca61cb28a9145c11ba5677cf24265d07f46d8d4"
    ).with_exposed_ports(4222) as nats:
        yield nats


def test_postgres_container(postgres):
    url = postgres.get_connection_url()
    assert url is not None
    # Basic connectivity check
    with psycopg.connect(url.replace("+psycopg2", "")) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            assert cur.fetchone() == (1,)


def test_redis_container(redis_client):
    client = redis_client.get_client()
    client.set("key", "value")
    assert client.get("key") == b"value"


@pytest.mark.asyncio
async def test_nats_container(nats_server):
    port = nats_server.get_exposed_port(4222)
    host = nats_server.get_container_host_ip()
    url = f"nats://{host}:{port}"

    nc = await nats.connect(url)
    assert nc.is_connected
    await nc.close()


@pytest.fixture(scope="module", autouse=True)
def unmock_redis():
    """Restore the real Redis classes for the disposable Redis integration test."""
    import importlib
    import sys

    import redis.asyncio
    import redis.asyncio.client

    patched_client_redis = redis.asyncio.client.Redis
    patched_asyncio_redis = redis.asyncio.Redis
    importlib.reload(redis.asyncio.client)
    real_redis = redis.asyncio.client.Redis
    redis.asyncio.client.Redis = real_redis
    redis.asyncio.Redis = real_redis

    base_module = "app.core.ratelimit.strategies.base"
    if base_module in sys.modules:
        importlib.reload(sys.modules[base_module])

    yield

    redis.asyncio.client.Redis = patched_client_redis
    redis.asyncio.Redis = patched_asyncio_redis
    if base_module in sys.modules:
        importlib.reload(sys.modules[base_module])


@pytest.mark.asyncio
async def test_totp_budget_concurrent_redis_checks_are_atomic(
    redis_client, monkeypatch, unmock_redis
):
    import asyncio
    import uuid

    import redis.asyncio
    from fastapi import HTTPException

    from app.auth.mfa.challenge import _enforce_totp_attempt_budget
    from app.core.config import settings
    from app.core.ratelimit.circuit_breaker import get_circuit_breaker
    from app.core.ratelimit.strategies.base import set_rate_limit_client_factory

    redis_url = f"redis://{redis_client.get_container_host_ip()}:{redis_client.get_exposed_port(6379)}"
    async_redis = redis.asyncio.Redis.from_url(redis_url)
    set_rate_limit_client_factory(lambda _url: async_redis)
    get_circuit_breaker.cache_clear()
    get_circuit_breaker().reset_for_testing()

    limit = 8
    window = 60
    user_id = uuid.uuid4()
    redis_key = f"rate-limit:mfa:totp-attempts:{user_id}"
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "redis")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", redis_url)
    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", limit)
    monkeypatch.setattr(settings, "mfa_challenge_ttl_seconds", window)

    try:
        results = await asyncio.gather(
            *(_enforce_totp_attempt_budget(user_id=user_id) for _ in range(32)),
            return_exceptions=True,
        )
        allowed = [result for result in results if result is None]
        denied = [result for result in results if isinstance(result, HTTPException)]
        unexpected = [
            result
            for result in results
            if result is not None and not isinstance(result, HTTPException)
        ]

        assert len(allowed) == limit
        assert len(denied) == 32 - limit
        assert all(result.status_code == 429 for result in denied)
        assert not unexpected
        assert await async_redis.zcard(redis_key) == limit
        ttl_ms = await async_redis.pttl(redis_key)
        assert 0 < ttl_ms <= window * 1000
    finally:
        try:
            await async_redis.delete(redis_key)
        finally:
            set_rate_limit_client_factory(None)
            await async_redis.aclose()
            get_circuit_breaker.cache_clear()
