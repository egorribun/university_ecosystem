"""Infrastructure startup, configuration, and adapter runtime contracts."""

from __future__ import annotations

import asyncio
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response

import app.api.deps.etag as etag_module
import app.core.middleware as middleware
import app.services.nats_messaging as nats_messaging
import app.utils.images_vips as images_vips
from app.api.deps.etag import cached_endpoint
from app.core.db import listeners
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.nats_broker import NatsTaskBroker
from app.core.ssrf import validate_public_https_url
from app.workers.outbox import OutboxWorker


def test_middleware_lazy_exports_and_unknown_attribute() -> None:
    from app.core.middleware.content_size import ContentSizeLimitMiddleware
    from app.core.middleware.setup import configure_middleware

    assert (
        middleware.__getattr__("ContentSizeLimitMiddleware")
        is ContentSizeLimitMiddleware
    )
    assert middleware.__getattr__("configure_middleware") is configure_middleware
    with pytest.raises(AttributeError, match="missing"):
        middleware.__getattr__("missing")


def test_tenant_listener_registration_is_idempotent() -> None:
    with (
        patch.object(listeners.event, "contains", return_value=True),
        patch.object(listeners.event, "listen") as listen,
    ):
        listeners.register_tenant_listeners()
    listen.assert_not_called()


@pytest.mark.asyncio
async def test_tenant_middleware_passthrough_and_empty_header_paths() -> None:
    downstream = AsyncMock()
    tenant_middleware = TenantContextMiddleware(downstream)
    receive = AsyncMock()
    send = AsyncMock()

    websocket_scope = {"type": "websocket"}
    await tenant_middleware(websocket_scope, receive, send)
    downstream.assert_awaited_once_with(websocket_scope, receive, send)

    downstream.reset_mock()
    http_scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 443),
    }
    await tenant_middleware(http_scope, receive, send)
    assert http_scope["state"]["tenant_id"] == ""


@pytest.mark.asyncio
async def test_cached_endpoint_omits_missing_optional_user_id_from_key() -> None:
    cache = MagicMock(enabled=True)
    cache.get = AsyncMock(
        return_value=SimpleNamespace(etag="cached-etag", payload={"cached": True})
    )
    resolver = MagicMock()
    resolver.get_version = AsyncMock(return_value="1")

    @cached_endpoint(resolver, "closure")
    async def endpoint(**kwargs: object) -> dict[str, bool]:
        return {"cached": False}

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 443),
        }
    )
    response = Response()
    with (
        patch.object(etag_module, "get_cache", return_value=cache),
        patch.object(etag_module, "etag_matches", return_value=False),
        patch.object(etag_module, "get_current_tenant", return_value="tenant"),
        patch.object(
            etag_module,
            "generate_cache_key",
            wraps=etag_module.generate_cache_key,
        ) as generate_cache_key,
    ):
        result = await endpoint(
            request=request,
            response=response,
            user=SimpleNamespace(id=None),
        )

    assert result == {"cached": True}
    params = generate_cache_key.call_args.kwargs["params"]
    assert "__authenticated_user_id" not in params
    assert params["__tenant_id"] == "tenant"


def test_public_https_literal_is_allowed_when_not_blocked() -> None:
    validate_public_https_url("https://8.8.8.8/push")


@pytest.mark.asyncio
async def test_outbox_heartbeat_optional_paths(tmp_path: Path) -> None:
    no_heartbeat = OutboxWorker(heartbeat_path=None)
    await no_heartbeat._heartbeat_loop()

    worker = OutboxWorker(heartbeat_path=tmp_path / "heartbeat", batch_size=1)
    worker._listen_loop = AsyncMock()
    worker._heartbeat_loop = AsyncMock()

    async def finish_batch() -> int:
        await asyncio.sleep(0)
        worker._is_running = False
        return worker.batch_size

    worker.process_batch = AsyncMock(side_effect=finish_batch)
    with patch("app.workers.outbox.asyncio.gather", new=AsyncMock()) as gather:
        await worker.run_forever()

    gather.assert_awaited_once()
    assert gather.await_args.kwargs["return_exceptions"] is True
    worker._heartbeat_loop.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_nats_broker_preserves_primary_error_when_cleanup_fails() -> None:
    broker = NatsTaskBroker()
    broker.close = AsyncMock(side_effect=OSError("cleanup failed"))
    with (
        patch(
            "app.core.nats_broker.nats.connect",
            new=AsyncMock(side_effect=ConnectionError("connect failed")),
        ),
        pytest.raises(ConnectionError, match="connect failed"),
    ):
        await broker.connect()
    broker.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_nats_service_connect_without_auth_token() -> None:
    client = MagicMock()
    client.jetstream.return_value = MagicMock()
    connect = AsyncMock(return_value=client)
    service = nats_messaging.NatsService(auth_token=None)
    with patch.object(nats_messaging.nats, "connect", new=connect):
        await service.connect()

    assert "token" not in connect.await_args.kwargs


def test_images_vips_import_success_path_with_optional_module() -> None:
    fake_pyvips = MagicMock()
    module_path = Path(images_vips.__file__)
    with patch.dict(sys.modules, {"pyvips": fake_pyvips}):
        namespace = runpy.run_path(str(module_path))

    assert namespace["VIPS_AVAILABLE"] is True
    assert namespace["pyvips"] is fake_pyvips
