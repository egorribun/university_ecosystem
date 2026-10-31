"""AUD-358 regressions for HTTP body limits on WebSocket-related paths."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.middleware.content_size import ContentSizeLimitMiddleware

_MAX_BYTES = 8


def _build_ticket_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ContentSizeLimitMiddleware, max_bytes=_MAX_BYTES)

    @app.post("/ws/ticket")
    async def issue_ticket(request: Request) -> JSONResponse:
        return JSONResponse({"length": len(await request.body())})

    return app


@pytest.mark.asyncio
async def test_http_ws_ticket_path_rejects_oversized_content_length() -> None:
    transport = ASGITransport(app=_build_ticket_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/ws/ticket", content=b"x" * (_MAX_BYTES + 1))

    assert response.status_code == 413
    assert response.json()["status"] == 413
    assert response.json()["detail"]
    assert response.headers["content-type"].startswith("application/problem+json")
    assert int(response.headers["content-length"]) == len(response.content)


@pytest.mark.asyncio
async def test_http_ws_ticket_path_rejects_oversized_streamed_body() -> None:
    async def request_chunks():
        yield b"x" * (_MAX_BYTES + 1)

    transport = ASGITransport(app=_build_ticket_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ws/ticket",
            content=request_chunks(),
            headers={"transfer-encoding": "chunked"},
        )

    assert response.status_code == 413
    assert response.json()["status"] == 413
    assert response.json()["detail"]
    assert response.headers["content-type"].startswith("application/problem+json")
    assert int(response.headers["content-length"]) == len(response.content)


@pytest.mark.asyncio
async def test_websocket_scope_still_passes_through() -> None:
    received: list[dict[str, Any]] = []
    called: list[str] = []

    async def websocket_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        called.append(scope["type"])
        await send({"type": "websocket.accept"})

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        received.append(message)

    scope = {"type": "websocket", "path": "/ws/chat"}
    middleware = ContentSizeLimitMiddleware(websocket_app, max_bytes=_MAX_BYTES)
    await middleware(scope, receive, send)

    assert called == ["websocket"]
    assert received == [{"type": "websocket.accept"}]


@pytest.mark.asyncio
async def test_streaming_response_chunks_still_pass_through() -> None:
    sent: list[dict[str, Any]] = []

    async def streaming_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await send(
            {"type": "http.response.body", "body": b"second", "more_body": False}
        )

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    middleware = ContentSizeLimitMiddleware(streaming_app, max_bytes=_MAX_BYTES)
    await middleware(scope, receive, send)

    assert sent == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"first", "more_body": True},
        {"type": "http.response.body", "body": b"second", "more_body": False},
    ]
