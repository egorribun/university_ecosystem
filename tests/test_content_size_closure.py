"""Closure tests for content-size dispatch and replay edge paths."""

from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.core.middleware.content_size import ContentSizeLimitMiddleware


def _request(
    *, headers: list[tuple[bytes, bytes]] | None = None, method: str = "POST"
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/upload",
        "query_string": b"",
        "headers": headers or [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive=receive)


@pytest.mark.asyncio
async def test_dispatch_reads_chunked_body_and_replays_to_app():
    app = AsyncMock()
    middleware = ContentSizeLimitMiddleware(app, max_bytes=100)
    request = _request()
    chunks = iter([b"small-body", b""])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": False}

    request = Request(request.scope, receive=receive)

    await middleware._dispatch(request, AsyncMock())

    app.assert_awaited_once()
    replayed_request = Request(app.await_args.args[0], receive=app.await_args.args[1])
    assert await replayed_request.body() == b"small-body"


@pytest.mark.asyncio
async def test_read_replay_uses_ram_buffer_without_tempfile():
    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=100)
    request = _request()
    chunks = iter([b"12345", b""])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": False}

    request = Request(request.scope, receive=receive)
    replay, rejected = await middleware._read_and_replay_body(request, AsyncMock())

    assert rejected is False
    assert replay is not None
    assert await replay.body() == b"12345"


@pytest.mark.asyncio
async def test_read_replay_fast_content_length_builds_replay_request():
    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=100)
    request = _request(headers=[(b"content-length", b"5")])
    chunks = iter([b"12345", b""])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": False}

    request = Request(request.scope, receive=receive)
    replay, rejected = await middleware._read_and_replay_body(request, AsyncMock())

    assert rejected is False
    assert replay is not None
    assert await replay.body() == b"12345"


@pytest.mark.asyncio
async def test_read_replay_rejects_before_tempfile_is_created():
    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=10)
    request = _request()
    chunks = iter([b"12345", b"678901"])
    send = AsyncMock()

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    request = Request(request.scope, receive=receive)
    with patch.object(ContentSizeLimitMiddleware, "_MEM_BUFFER_THRESHOLD", 20):
        replay, rejected = await middleware._read_and_replay_body(request, send)

    assert replay is None
    assert rejected is True
    assert send.await_count >= 2


@pytest.mark.asyncio
async def test_dispatch_stops_after_chunked_payload_rejection():
    app = AsyncMock()
    middleware = ContentSizeLimitMiddleware(app, max_bytes=4)
    request = _request()

    async def receive():
        return {"type": "http.request", "body": b"too-large", "more_body": False}

    request = Request(request.scope, receive=receive)
    await middleware._dispatch(request, AsyncMock())

    app.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_keeps_original_request_when_replay_builder_returns_none():
    app = AsyncMock()
    middleware = ContentSizeLimitMiddleware(app, max_bytes=100)
    request = _request()

    with patch.object(
        middleware,
        "_read_and_replay_body",
        new=AsyncMock(return_value=(None, False)),
    ):
        await middleware._dispatch(request, AsyncMock())

    app.assert_awaited_once()



@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["ram", "spill", "declared"])
async def test_replay_delivers_body_once_then_original_disconnect(path, monkeypatch):
    payload = b"replayed-body"
    headers = (
        [(b"content-length", str(len(payload)).encode())] if path == "declared" else []
    )
    request = _request(headers=headers)
    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=100)
    if path == "spill":
        monkeypatch.setattr(middleware, "_MEM_BUFFER_THRESHOLD", 1)
    messages = iter(
        [
            {"type": "http.request", "body": payload, "more_body": False},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(messages)

    request = Request(request.scope, receive=receive)
    replay, rejected = await middleware._read_and_replay_body(request, AsyncMock())
    assert not rejected
    assert replay is not None
    assert await replay.receive() == {
        "type": "http.request",
        "body": payload,
        "more_body": False,
    }
    assert await replay.receive() == {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_replay_preserves_starlette_consumed_request_disconnect():
    from starlette.middleware.base import _CachedRequest

    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=100)
    request = _request()
    messages = iter(
        [
            {"type": "http.request", "body": b"body", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(messages)

    replay, rejected = await middleware._read_and_replay_body(
        Request(request.scope, receive=receive), AsyncMock()
    )
    assert not rejected
    assert replay is not None
    downstream = _CachedRequest(replay.scope, replay.receive)
    assert (await downstream.wrapped_receive())["body"] == b"body"
    assert await downstream.wrapped_receive() == {"type": "http.disconnect"}



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("receive failed"), asyncio.CancelledError()]
)
async def test_replay_preserves_original_receive_failure(failure):
    middleware = ContentSizeLimitMiddleware(AsyncMock(), max_bytes=100)
    request = _request()
    consumed = False

    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": b"body", "more_body": False}
        raise failure

    replay, rejected = await middleware._read_and_replay_body(
        Request(request.scope, receive=receive), AsyncMock()
    )
    assert not rejected
    assert replay is not None
    assert (await replay.receive())["body"] == b"body"
    with pytest.raises(type(failure)) as caught:
        await replay.receive()
    assert caught.value is failure
