"""WebSocket upgrades are bound to the configured MVP tenant before any handler runs.

The HTTP path resolves tenant scope in TenantContextMiddleware. Before this gate
the middleware forwarded every non-HTTP scope untouched, so the cookie credential
was never checked against the MVP tenant and the handler's database session ran
with an empty tenant context. Row-level security then hid every tenant row from it.
"""

from __future__ import annotations

from typing import Any
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
