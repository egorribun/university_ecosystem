"""WebSocket upgrades are bound to the configured MVP tenant before any handler runs.

The HTTP path resolves tenant scope in TenantContextMiddleware. Before this gate
the middleware forwarded every non-HTTP scope untouched, so the cookie credential
was never checked against the MVP tenant and the handler's database session ran
with an empty tenant context. Row-level security then hid every tenant row from it.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth import security
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx

_COOKIE = {"cookie": "access_token_v2=opaque-token"}


def _probe_app(tenant: Any) -> tuple[FastAPI, list[str]]:
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=tenant)
    seen: list[str] = []

    @app.websocket("/ws/probe")
    async def probe(websocket: WebSocket) -> None:
        seen.append(get_current_tenant())
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    return app, seen


def test_unconfigured_deployment_leaves_websocket_scope_unchanged() -> None:
    app, seen = _probe_app(None)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/probe", headers=_COOKIE) as session:
            assert session.receive_text() == "ok"
    assert seen == [""]


def test_upgrade_without_cookie_binds_the_configured_tenant() -> None:
    tenant = uuid4()
    app, seen = _probe_app(tenant)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/probe?ticket=" + "a" * 64) as session:
            assert session.receive_text() == "ok"
    assert seen == [str(tenant)]


def test_matching_cookie_binds_tenant_and_restores_caller_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = uuid4()
    monkeypatch.setattr(
        security, "decode_token", lambda token: {"tenant_id": str(tenant)}
    )
    app, seen = _probe_app(tenant)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/probe", headers=_COOKIE) as session:
            assert session.receive_text() == "ok"
    assert seen == [str(tenant)]
    assert get_current_tenant() == ""
    assert bypass_rls_ctx.get() is False
    assert tenant_id_ctx.get() == ""


@pytest.mark.parametrize("claims", [None, {"tenant_id": str(uuid4())}, {}])
def test_cookie_from_another_or_undecodable_tenant_is_refused_before_handshake(
    monkeypatch: pytest.MonkeyPatch, claims: dict[str, str] | None
) -> None:
    tenant = uuid4()
    monkeypatch.setattr(security, "decode_token", lambda token: claims)
    app, seen = _probe_app(tenant)
    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect("/ws/probe", headers=_COOKIE) as session,
        ):
            session.receive_text()
    assert refused.value.code == 1008
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, RuntimeError, asyncio.CancelledError])
async def test_upgrade_restores_existing_context_in_the_calling_task(
    failure: type[BaseException] | None,
) -> None:
    tenant = uuid4()
    previous_tenant = str(uuid4())
    seen: list[str] = []

    async def downstream(scope: dict[str, Any], receive: Any, send: Any) -> None:
        assert scope["state"]["tenant_id"] == str(tenant)
        assert get_current_tenant() == str(tenant)
        assert bypass_rls_ctx.get() is False
        seen.append(get_current_tenant())
        if failure is not None:
            raise failure("synthetic upgrade termination")

    middleware = TenantContextMiddleware(downstream, mvp_tenant_id=tenant)
    scope = {"type": "websocket", "headers": []}
    tenant_token = tenant_id_ctx.set(previous_tenant)
    bypass_token = bypass_rls_ctx.set(True)
    try:
        if failure is None:
            await middleware(scope, AsyncMock(), AsyncMock())
        else:
            with pytest.raises(failure):
                await middleware(scope, AsyncMock(), AsyncMock())
        assert seen == [str(tenant)]
        assert get_current_tenant() == previous_tenant
        assert bypass_rls_ctx.get() is True
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


@pytest.mark.parametrize("query", ["", "?ticket=invalid"])
def test_tenant_binding_does_not_authenticate_the_actual_chat_route(
    query: str,
) -> None:
    from app.api import websocket as websocket_api

    tenant = uuid4()
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware, mvp_tenant_id=tenant)
    app.include_router(websocket_api.router)
    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect(
                "/ws/chat" + query, headers={"x-tenant-id": str(uuid4())}
            ),
        ):
            pytest.fail("An unauthenticated socket must never be accepted")
    assert refused.value.code == 4001
