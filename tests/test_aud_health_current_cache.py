"""The health probe must see cache-adapter cleanup failures."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api import health
from app.core import health as core_health
from app.deps import cache as cache_module
from app.main import app


@pytest.fixture
def available_dependencies(monkeypatch: pytest.MonkeyPatch):
    health.reset_health_cache()
    health.reset_shutdown_flag()
    connection = SimpleNamespace(execute=AsyncMock())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(health, "engine", SimpleNamespace(connect=lambda: context))
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(environment="testing", event_file_scanner_enabled=False),
    )
    monkeypatch.setattr(health, "_check_queue", AsyncMock())
    monkeypatch.setattr(health, "_probe_storage", AsyncMock(return_value=("ok", 0.0)))
    monkeypatch.setattr(health, "get_pool_health_metrics", lambda: {"size": 3})
    monkeypatch.setattr(health, "record_health_probe", MagicMock())
    monkeypatch.setattr(health, "wait_db", AsyncMock())
    monkeypatch.setattr(
        core_health, "check_spicedb_health", AsyncMock(return_value=("ok", 1.0))
    )
    yield
    health.reset_health_cache()
    health.reset_shutdown_flag()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["redis", "tiered", "cluster"])
async def test_http_cache_failure_when_real_redis_adapter_cannot_delete(
    available_dependencies, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    adapter_type = (
        cache_module.RedisClusterCache if kind == "cluster" else cache_module.RedisCache
    )
    shared = adapter_type("redis://localhost:6379/0", default_ttl=60)
    shared._client = redis
    cache = (
        cache_module.TieredCache(cache_module.MemoryCache(), shared)
        if kind == "tiered"
        else shared
    )
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    real_delete = redis.delete
    attempts: list[tuple[str, ...]] = []

    async def failed_delete(*keys: str) -> int:
        attempts.append(keys)
        raise RedisConnectionError("probe cleanup unavailable")

    monkeypatch.setattr(redis, "delete", failed_delete)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            failed = await client.get("/healthz?brief=false")
            assert failed.status_code == 503
            assert failed.json()["status"] == "error"
            assert failed.json()["cache"] == "error"
            assert "pool" not in failed.json()
            assert not any(key.endswith("_latency_ms") for key in failed.json())
            assert len(attempts) == 1 and len(attempts[0]) == 1
            assert await redis.get(attempts[0][0]) is not None

            # A fresh cached result stays consistent until its cache is cleared.
            monkeypatch.setattr(redis, "delete", real_delete)
            cached = await client.get("/healthz")
            assert cached.status_code == 503 and cached.json() == failed.json()
            full = await health.healthz()
            assert full.status_code == 503
            assert json.loads(full.body)["pool"] == {"size": 3}
            live = await client.get("/health/live")
            ready = await client.get("/health/ready")
            assert live.status_code == 200 and live.json() == {"status": "alive"}
            assert ready.status_code == 200 and ready.json() == {"status": "ready"}

            health.reset_health_cache()
            recovered = await client.get("/healthz")
            assert recovered.status_code == 200
            assert recovered.json()["status"] == "ok"
            assert recovered.json()["cache"] == "ok"
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_http_cache_failure_when_real_nats_adapter_cannot_delete(
    available_dependencies, monkeypatch: pytest.MonkeyPatch
) -> None:
    class KV:
        def __init__(self) -> None:
            self.values: dict[str, bytes] = {}
            self.fail_delete = True

        async def put(self, key: str, value: bytes) -> None:
            self.values[key] = value

        async def get(self, key: str) -> SimpleNamespace | None:
            value = self.values.get(key)
            return None if value is None else SimpleNamespace(value=value)

        async def delete(self, key: str) -> None:
            if self.fail_delete:
                raise OSError("probe cleanup unavailable")
            self.values.pop(key, None)

    kv = KV()
    cache = cache_module.NatsKVCache(bucket="health-test", default_ttl=60)
    cache._kv = kv
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        failed = await client.get("/healthz")
        assert failed.status_code == 503
        assert failed.json()["cache"] == "error"
        assert len(kv.values) == 1
        kv.fail_delete = False
        health.reset_health_cache()
        recovered = await client.get("/healthz")
        assert recovered.status_code == 200
        assert recovered.json()["cache"] == "ok"
        assert len(kv.values) == 1


@pytest.mark.asyncio
async def test_missing_tiered_shared_cache_is_not_reported_as_healthy(
    available_dependencies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cache_module,
        "settings",
        SimpleNamespace(
            cache_enabled=True,
            cache_backend_normalized="tiered",
            cache_default_ttl_seconds=60,
            cache_l1_ttl_seconds=60,
            cache_redis_url="",
        ),
    )
    cache = cache_module.create_cache_backend()
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["cache"] == "error"
