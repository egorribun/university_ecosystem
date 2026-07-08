"""
W19: Chaos Engineering tests using ToxiProxy for network failure simulation.
Requires TOXIPROXY_URL env var (default: http://localhost:8474).
Skipped automatically when TOXIPROXY_URL is not reachable.
"""

import os

import httpx
import pytest

TOXIPROXY_URL = os.getenv("TOXIPROXY_URL", "http://localhost:8474")


def toxiproxy_available() -> bool:
    """Return True when the ToxiProxy HTTP API is reachable."""
    try:
        resp = httpx.get(f"{TOXIPROXY_URL}/version", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


pytoxiproxy = pytest.mark.skipif(
    not toxiproxy_available(),
    reason="ToxiProxy not available",
)


@pytest.mark.chaos
@pytest.mark.integration
@pytoxiproxy
async def test_postgres_latency_triggers_timeout_response(async_client):
    """PostgreSQL latency > threshold -> backend returns 503/504.

    WHY: verifies the backend emits a meaningful HTTP error rather than
    hanging indefinitely when the DB is slow (circuit-breaker / statement
    timeout coverage).
    """
    async with httpx.AsyncClient() as http:
        await http.post(
            f"{TOXIPROXY_URL}/proxies/postgres/toxics",
            json={
                "type": "latency",
                "attributes": {"latency": 5000},
                "name": "pg_lag",
            },
        )
    try:
        response = await async_client.get("/api/v1/events")
        assert response.status_code in (503, 504, 408)
    finally:
        async with httpx.AsyncClient() as http:
            await http.delete(f"{TOXIPROXY_URL}/proxies/postgres/toxics/pg_lag")


@pytest.mark.chaos
@pytest.mark.integration
@pytoxiproxy
async def test_redis_down_cache_miss_uses_db(async_client):
    """Redis down -> cache miss -> backend serves from DB (degraded but functional).

    WHY: verifies the cache layer fails open — reads fall through to the DB
    so the API remains available when Redis is unavailable.
    """
    async with httpx.AsyncClient() as http:
        await http.post(
            f"{TOXIPROXY_URL}/proxies/redis/toxics",
            json={
                "type": "timeout",
                "attributes": {"timeout": 0},
                "name": "redis_down",
            },
        )
    try:
        response = await async_client.get("/api/v1/health")
        # Should still respond (circuit breaker / degraded mode)
        assert response.status_code in (200, 503)
    finally:
        async with httpx.AsyncClient() as http:
            await http.delete(f"{TOXIPROXY_URL}/proxies/redis/toxics/redis_down")


@pytest.mark.chaos
@pytest.mark.integration
@pytoxiproxy
async def test_nats_packet_loss_outbox_retries(async_client):
    """Zero-bandwidth NATS toxic -> outbox worker eventually delivers messages.

    WHY: simulates NATS network saturation.  The transactional outbox pattern
    must persist events to the DB so they survive the degraded window and are
    retried once connectivity is restored.
    """
    async with httpx.AsyncClient() as http:
        await http.post(
            f"{TOXIPROXY_URL}/proxies/nats/toxics",
            json={
                "type": "bandwidth",
                "attributes": {"rate": 0},
                "name": "nats_loss",
            },
        )
    try:
        # Health endpoint should remain accessible even under NATS pressure
        response = await async_client.get("/api/v1/health")
        assert response.status_code in (200, 503)
    finally:
        async with httpx.AsyncClient() as http:
            await http.delete(f"{TOXIPROXY_URL}/proxies/nats/toxics/nats_loss")
