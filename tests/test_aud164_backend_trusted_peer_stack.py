"""AUD-164: exercise the configured backend stack with synthetic ASGI peers.

These in-process requests do not establish ownership of network peers or prove
the deployed Caddy, gateway, Gunicorn, Redis, or Kubernetes topology.
"""

from __future__ import annotations

import secrets
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI, Request

from app.core.config import settings
from app.core.middleware.setup import configure_middleware
from app.core.ratelimit import resolve_client_ip, sensitive_route_limit

_CLIENT_A = "172.23.0.10"
_CLIENT_B = "172.24.0.10"
_CADDY = "172.23.0.20"
_GATEWAY = "172.23.0.30"


@pytest.mark.parametrize(
    ("path", "uses_dependency"),
    [
        ("/api/v1/auth/login/json", False),
        ("/api/v1/auth/register", False),
        ("/api/v1/password/forgot", False),
        ("/api/v1/auth/mfa/verify", True),
    ],
    ids=("login", "registration", "password-reset", "mfa"),
)
@pytest.mark.asyncio
async def test_trusted_forwarding_and_direct_spoof_share_the_right_buckets(
    monkeypatch: pytest.MonkeyPatch, path: str, uses_dependency: bool
) -> None:
    monkeypatch.setattr(
        settings, "trusted_proxies_list", [_CADDY, "172.24.0.20", _GATEWAY]
    )
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "rate_limit_default_list", ["200/minute"])
    monkeypatch.setattr(settings, "rate_limit_headers_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_login", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_auth_register", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_auth_password_reset", "2/minute")
    monkeypatch.setattr(settings, "allowed_hosts_list", ["testserver"])
    monkeypatch.setattr(settings, "csrf_hmac_secret", secrets.token_urlsafe(32))

    app = FastAPI()
    dependencies = (
        [
            Depends(
                sensitive_route_limit(
                    limit=2, window_sec=60, key_prefix=f"aud164-{uuid4().hex}"
                )
            )
        ]
        if uses_dependency
        else []
    )

    @app.get("/api/v1/auth/csrf-cookie")
    async def csrf_cookie() -> dict[str, bool]:
        return {"ok": True}

    @app.post(path, dependencies=dependencies)
    async def limited(request: Request) -> dict[str, str]:
        return {"client": resolve_client_ip(request)}

    configure_middleware(app, settings)

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(_GATEWAY, 50001)),
            base_url="https://testserver",
            headers={"X-Forwarded-For": f"{_CLIENT_A}, {_CADDY}"},
        ) as client_a,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(_GATEWAY, 50002)),
            base_url="https://testserver",
            headers={"X-Forwarded-For": f"{_CLIENT_B}, {_CADDY}"},
        ) as client_b,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(_CLIENT_A, 50003)),
            base_url="https://testserver",
        ) as direct_a,
    ):
        for client in (client_a, client_b, direct_a):
            setup = await client.get("/api/v1/auth/csrf-cookie")
            assert setup.status_code == 200
            csrf = client.cookies.get("csrf_token")
            assert csrf
            client.headers["X-CSRF-Token"] = csrf

        first = await client_a.post(path)
        second = await client_a.post(path)
        blocked = await client_a.post(path)
        other_client = await client_b.post(path)
        spoofed_xff = await client_a.post(
            path,
            headers={"X-Forwarded-For": f"{_CLIENT_B}, {_CLIENT_A}, {_CADDY}"},
        )
        spoofed_real_ip = await client_a.post(path, headers={"X-Real-IP": _CLIENT_B})
        spoofed_forwarded = await client_a.post(
            path, headers={"Forwarded": f"for={_CLIENT_B}"}
        )
        direct_xff = await direct_a.post(path, headers={"X-Forwarded-For": _CLIENT_B})
        direct_real_ip = await direct_a.post(path, headers={"X-Real-IP": _CLIENT_B})
        direct_forwarded = await direct_a.post(
            path, headers={"Forwarded": f"for={_CLIENT_B}"}
        )

    assert first.status_code == second.status_code == other_client.status_code == 200
    assert first.json() == second.json() == {"client": _CLIENT_A}
    assert other_client.json() == {"client": _CLIENT_B}
    assert [
        response.status_code
        for response in (
            blocked,
            spoofed_xff,
            spoofed_real_ip,
            spoofed_forwarded,
            direct_xff,
            direct_real_ip,
            direct_forwarded,
        )
    ] == [429] * 7
    expected_header_limit = "200" if uses_dependency else "2"
    assert all(
        response.headers["X-RateLimit-Limit"] == expected_header_limit
        for response in (first, second, blocked, other_client)
    )
