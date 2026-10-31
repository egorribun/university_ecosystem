"""A process-local cache remains healthy after the probe cleanup change."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import health
from app.deps.cache import MemoryCache
from app.main import app
from tests.test_aud_health_current_cache import (
    available_dependencies as available_dependencies,
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("available_dependencies")
async def test_memory_cache_remains_healthy_and_probe_key_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCache()
    monkeypatch.setattr(health, "get_cache", lambda: cache)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["cache"] == "ok"
    assert not cache._entries
