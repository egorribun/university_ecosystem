"""Owned probe attribution across real backend rate-limit layers.

This is in-process ASGI evidence, not Caddy, gateway, or owned deployment proof.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.auth.schemas import MfaVerifyIn
from app.core.config import settings
from app.core.config.mixins.rate_limit_settings import RateLimitSettingsMixin
from app.core.middleware.setup import _configure_rate_limiting
from app.core.ratelimit import sensitive_route_limit


@pytest.mark.asyncio
async def test_mfa_probe_keeps_dependency_limit_distinct_from_middleware_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RateLimitSettingsMixin()
    assert config.rate_limit_default_list == ["200/minute"]
    assert config.rate_limit_auth_mfa == "5/minute"
    config.rate_limit_storage_backend = "memory"
    config.rate_limit_storage_uri = "memory://"
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")

    app = FastAPI()
    _configure_rate_limiting(app, config)
    reached_handler = False
    dependency = sensitive_route_limit(
        limit_value=config.rate_limit_auth_mfa,
        key_prefix=f"owned-probe-mfa-{uuid.uuid4().hex}",
    )

    @app.post("/api/v1/auth/mfa/verify", dependencies=[Depends(dependency)])
    async def verify(payload: MfaVerifyIn) -> dict[str, str]:
        nonlocal reached_handler
        reached_handler = True
        return {"status": "unexpected"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("172.23.0.10", 49152)),
        base_url="http://testserver",
    ) as client:
        observations: list[httpx.Response] = []
        for _ in range(6):
            observations.append(await client.post("/api/v1/auth/mfa/verify", json={}))

    assert [response.status_code for response in observations] == [
        422,
        422,
        422,
        422,
        422,
        429,
    ]
    observed_limits = {
        response.headers["x-ratelimit-limit"] for response in observations
    }
    assert observed_limits == {"200"}
    assert not reached_handler
