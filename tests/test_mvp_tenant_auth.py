"""Operator tenant routing is not client authentication or an RLS bypass."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.config.app_gen import AppGeneralSettings
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.tenant import (
    bypass_rls_ctx,
    get_current_tenant,
    require_mvp_tenant,
    tenant_id_ctx,
)
from app.services.session_service import SessionService


@pytest.mark.parametrize(
    "headers",
    [
        {"x-user-id": "supplied"},
        {"x-session-id": "supplied"},
        {"x-internal-signature": "invalid"},
        {"authorization": "Bearer malformed"},
        {"authorization": "Basic malformed"},
        {"cookie": "access_token_v2=malformed"},
    ],
)
def test_invalid_supplied_identity_never_becomes_anonymous(
    headers: dict[str, str],
) -> None:
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=uuid4())
    called = []

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        called.append(True)
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe", headers=headers)
    assert response.status_code == 401
    assert not called
    if "cookie" in headers:
        assert "Max-Age=0" in response.headers["set-cookie"]


def test_operator_routing_does_not_authenticate_protected_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.deps.auth import _resolve_current_user

    tenant = uuid4()
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant)
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=tenant)
    db = MagicMock(execute=AsyncMock())

    @app.get("/protected")
    async def protected(request: Request) -> dict[str, str]:
        assert get_current_tenant() == str(tenant)
        await _resolve_current_user(request, None, db, MagicMock())
        return {"unexpected": "authenticated"}

    with TestClient(app) as client:
        response = client.get("/protected")
    assert response.status_code == 401
    db.execute.assert_not_awaited()


def test_operator_tenant_config_is_explicit_uuid() -> None:
    assert AppGeneralSettings(environment="testing").mvp_tenant_id is None
    tenant = uuid4()
    assert (
        AppGeneralSettings(
            environment="testing", mvp_tenant_id=str(tenant)
        ).mvp_tenant_id
        == tenant
    )
    for invalid in ("", "university", "not-a-uuid"):
        with pytest.raises(ValidationError):
            AppGeneralSettings(environment="testing", mvp_tenant_id=invalid)


def test_operator_scope_ignores_unsigned_routing_hint_and_restores_context() -> None:
    tenant, foreign = uuid4(), uuid4()
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=tenant)

    @app.get("/probe")
    async def probe(request: Request) -> dict[str, str]:
        return {"tenant": get_current_tenant(), "state": request.state.tenant_id}

    before = get_current_tenant()
    with TestClient(app) as client:
        response = client.get("/probe", headers={"x-tenant-id": str(foreign)})
    assert response.json() == {"tenant": str(tenant), "state": str(tenant)}
    assert get_current_tenant() == before


def test_signed_foreign_tenant_cannot_switch_operator_scope() -> None:
    tenant, foreign, user, session = (uuid4() for _ in range(4))
    signing_key = uuid4().hex
    app = FastAPI()
    app.add_middleware(
        TenantContextMiddleware, internal_hmac_secret=signing_key, mvp_tenant_id=tenant
    )
    called = []

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        called.append(True)
        return {"ok": True}

    signature = hmac.new(
        signing_key.encode(), f"{user}:{session}:{foreign}".encode(), hashlib.sha256
    ).hexdigest()
    with TestClient(app) as client:
        response = client.get(
            "/probe",
            headers={
                "x-user-id": str(user),
                "x-session-id": str(session),
                "x-tenant-id": str(foreign),
                "x-internal-signature": signature,
            },
        )
    assert response.status_code == 401
    assert not called


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [True, False])
async def test_session_requires_active_configured_tenant(
    monkeypatch: pytest.MonkeyPatch, active: bool
) -> None:
    tenant = uuid4()
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tenant if active else None
    db.execute = AsyncMock(return_value=result)
    token = tenant_id_ctx.set(str(tenant))
    try:
        if active:
            assert await require_mvp_tenant(db) == tenant
        else:
            with pytest.raises(HTTPException) as exc:
                await require_mvp_tenant(db)
            assert exc.value.status_code == 503
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_scope,bypass", [(True, False), (False, True)])
async def test_scope_mismatch_and_bypass_refused_before_query(
    monkeypatch: pytest.MonkeyPatch, foreign_scope: bool, bypass: bool
) -> None:
    tenant = uuid4()
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant)
    db = MagicMock(execute=AsyncMock())
    t = tenant_id_ctx.set(str(uuid4() if foreign_scope else tenant))
    b = bypass_rls_ctx.set(bypass)
    try:
        with pytest.raises(HTTPException):
            await require_mvp_tenant(db)
        db.execute.assert_not_awaited()
    finally:
        tenant_id_ctx.reset(t)
        bypass_rls_ctx.reset(b)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["configured", "foreign", "missing"])
async def test_token_uses_locked_stored_tenant_not_extra_claim(
    monkeypatch: pytest.MonkeyPatch, stored: str
) -> None:
    tenant, user = uuid4(), uuid4()
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant)
    active = MagicMock()
    active.scalar_one_or_none.return_value = tenant
    locked = MagicMock()
    stored_tenant = (
        tenant if stored == "configured" else uuid4() if stored == "foreign" else None
    )
    locked.one_or_none.return_value = (user, 0, True, stored_tenant)
    db = MagicMock(execute=AsyncMock(side_effect=[active, locked]), commit=AsyncMock())
    repo = SimpleNamespace(db=db, create=AsyncMock(return_value=SimpleNamespace()))
    service = SessionService(SimpleNamespace(sessions=repo))
    mint = MagicMock(return_value="opaque-token")
    monkeypatch.setattr(service, "_mint_jwt", mint)
    monkeypatch.setattr(service, "_enforce_concurrent_limit", AsyncMock())
    monkeypatch.setattr(service, "_sync_to_redis", AsyncMock())
    token = tenant_id_ctx.set(str(tenant))
    try:
        if stored == "configured":
            await service.create_access_token(
                user, extra_claims={"tenant_id": str(uuid4())}
            )
            assert mint.call_args.args[4]["tenant_id"] == str(tenant)
        else:
            with pytest.raises(HTTPException) as exc:
                await service.create_access_token(user)
            assert exc.value.status_code == 401
            repo.create.assert_not_awaited()
            mint.assert_not_called()
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_metrics_basic_auth_remains_an_independent_protected_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import base64

    import httpx

    from app.core import metrics

    username, password = uuid4().hex, uuid4().hex
    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_basic_auth_username", username)
    monkeypatch.setattr(settings, "metrics_basic_auth_password", password)
    monkeypatch.setattr(settings, "metrics_allowlist", ["127.0.0.1"])
    monkeypatch.setattr(metrics, "refresh_runtime_metrics", AsyncMock())
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=uuid4())
    app.add_api_route("/metrics", metrics.metrics_endpoint, methods=["GET"])
    good = base64.b64encode(f"{username}:{password}".encode()).decode()
    bad = base64.b64encode(f"{username}:incorrect".encode()).decode()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://owned.test"
    ) as client:
        assert (
            await client.get("/metrics", headers={"authorization": f"Basic {good}"})
        ).status_code == 200
        rejected = await client.get(
            "/metrics", headers={"authorization": f"Basic {bad}"}
        )
        assert rejected.status_code == 401
        assert rejected.headers["www-authenticate"] == 'Basic realm="Metrics"'
        assert (
            await client.get("/metrics", headers={"authorization": "Basic malformed"})
        ).status_code == 401
        assert (
            await client.get(
                "/metrics",
                headers={"authorization": f"Basic {good}", "x-user-id": "untrusted"},
            )
        ).status_code == 401
    transport = httpx.ASGITransport(app=app, client=("192.0.2.1", 1234))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://owned.test"
    ) as client:
        assert (
            await client.get("/metrics", headers={"authorization": f"Basic {good}"})
        ).status_code == 403
