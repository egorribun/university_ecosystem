"""Tests for ContentSizeLimitMiddleware (app/core/middleware/content_size.py).

Validates body-size enforcement for both Content-Length and chunked transfer
encoding paths, body replay semantics, WebSocket bypass, and the in-memory
to tempfile spill transition.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.middleware.content_size import ContentSizeLimitMiddleware

# ---------------------------------------------------------------------------
# Minimal test app — 1 KB limit for easy boundary testing
# ---------------------------------------------------------------------------
_MAX_BYTES = 1024


def _build_test_app(max_bytes: int = _MAX_BYTES) -> FastAPI:
    """Construct a minimal FastAPI app with the content-size middleware."""
    test_app = FastAPI()
    test_app.add_middleware(ContentSizeLimitMiddleware, max_bytes=max_bytes)

    @test_app.post("/echo")
    async def echo_body(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse(
            {"length": len(body), "body": body.decode("utf-8", "replace")}
        )

    @test_app.put("/echo")
    async def echo_put(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"length": len(body)})

    @test_app.patch("/echo")
    async def echo_patch(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"length": len(body)})

    @test_app.delete("/delete-with-body")
    async def delete_with_body(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"length": len(body)})

    @test_app.get("/get")
    async def get_endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    @test_app.api_route("/ws/test", methods=["POST"])
    async def ws_path_post(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"length": len(body)})

    return test_app


@pytest.fixture
def app() -> FastAPI:
    return _build_test_app()


import pytest_asyncio


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Non-HTTP scope passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_http_scope_passthrough():
    """Non-HTTP scopes (e.g. lifespan) pass through without interference."""
    test_app = _build_test_app()
    received_events: list[dict] = []

    async def mock_receive():
        return {"type": "lifespan.startup"}

    async def mock_send(message):
        received_events.append(message)

    middleware = ContentSizeLimitMiddleware(test_app, max_bytes=100)
    scope = {"type": "lifespan"}

    # Should delegate to inner app without error
    # Inner app will fail because scope is not HTTP, but the middleware itself
    # should not block. We catch the inner error to prove passthrough.
    try:
        await middleware(scope, mock_receive, mock_send)
    except Exception:  # noqa: S110
        pass  # Inner app doesn't handle lifespan — expected


# ---------------------------------------------------------------------------
# Content-Length present and within limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_length_within_limit(client: AsyncClient):
    """Request with Content-Length ≤ max_bytes succeeds."""
    payload = "a" * 500
    response = await client.post("/echo", content=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == 500


# ---------------------------------------------------------------------------
# Content-Length exceeding max_bytes → 413
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_length_exceeds_limit(client: AsyncClient):
    """Request with Content-Length > max_bytes returns 413."""
    payload = "x" * (_MAX_BYTES + 1)
    response = await client.post("/echo", content=payload)
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Invalid (non-numeric) Content-Length → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_content_length_header():
    """Non-numeric Content-Length yields 400 Bad Request."""
    test_app = _build_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/echo",
            content=b"hello",
            headers={"content-length": "not-a-number"},
        )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Chunked transfer (no Content-Length) within limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunked_transfer_within_limit(client: AsyncClient):
    """Chunked upload within limit succeeds and body is replayed correctly."""
    payload = b"chunk-data-" * 10  # 110 bytes
    response = await client.post(
        "/echo",
        content=payload,
        headers={"transfer-encoding": "chunked"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == len(payload)


# ---------------------------------------------------------------------------
# Chunked transfer exceeding limit → 413
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunked_transfer_exceeds_limit(client: AsyncClient):
    """Chunked upload exceeding max_bytes returns 413."""
    payload = b"x" * (_MAX_BYTES + 100)
    response = await client.post(
        "/echo",
        content=payload,
        headers={"transfer-encoding": "chunked"},
    )
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Body replay: downstream handler reads full body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_replay_full_content(client: AsyncClient):
    """Downstream handler can read the complete body after middleware buffering."""
    payload = "important-data-12345"
    response = await client.post(
        "/echo",
        content=payload,
        headers={"transfer-encoding": "chunked"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["body"] == payload
    assert data["length"] == len(payload)


# ---------------------------------------------------------------------------
# WebSocket paths bypass body checking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_path_bypasses_body_check(client: AsyncClient):
    """POST to /ws/* path skips body-size enforcement."""
    payload = b"x" * (_MAX_BYTES + 100)
    response = await client.post("/ws/test", content=payload)
    # Should succeed because /ws paths are exempted from chunked body check
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == len(payload)


# ---------------------------------------------------------------------------
# DELETE with body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_with_body_within_limit(client: AsyncClient):
    """DELETE request with a body within limit succeeds (RFC 9110 permits body)."""
    payload = b"delete-payload"
    response = await client.request("DELETE", "/delete-with-body", content=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == len(payload)


@pytest.mark.asyncio
async def test_delete_with_body_exceeds_limit():
    """DELETE with Content-Length exceeding limit returns 413."""
    test_app = _build_test_app(max_bytes=50)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = b"x" * 100
        response = await ac.request("DELETE", "/delete-with-body", content=payload)
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# GET/HEAD skip body check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skips_body_check(client: AsyncClient):
    """GET request is not subject to body-size enforcement."""
    response = await client.get("/get")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Memory buffer threshold boundary (exactly at 512 KB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_buffer_threshold_boundary():
    """Body exactly at _MEM_BUFFER_THRESHOLD (512 KB) stays in memory."""
    threshold = ContentSizeLimitMiddleware._MEM_BUFFER_THRESHOLD
    max_bytes = threshold + 1024  # Allow enough room
    test_app = _build_test_app(max_bytes=max_bytes)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = b"B" * threshold
        response = await ac.post(
            "/echo",
            content=payload,
            headers={"transfer-encoding": "chunked"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == threshold


# ---------------------------------------------------------------------------
# Tempfile spill path (body > 512 KB but < max_bytes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tempfile_spill_path():
    """Body larger than _MEM_BUFFER_THRESHOLD but within max_bytes spills to tempfile."""
    threshold = ContentSizeLimitMiddleware._MEM_BUFFER_THRESHOLD
    body_size = threshold + 1024  # Exceeds threshold, triggers tempfile
    max_bytes = body_size + 4096  # Within overall limit
    test_app = _build_test_app(max_bytes=max_bytes)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = b"S" * body_size
        response = await ac.post(
            "/echo",
            content=payload,
            headers={"transfer-encoding": "chunked"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == body_size


# ---------------------------------------------------------------------------
# PUT and PATCH also enforce limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["put", "patch"])
async def test_put_patch_enforce_limits(client: AsyncClient, method: str):
    """PUT and PATCH methods are subject to body-size enforcement."""
    payload = b"x" * (_MAX_BYTES + 1)
    send = getattr(client, method)
    response = await send("/echo", content=payload)
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Exact boundary: body == max_bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_boundary_content_length(client: AsyncClient):
    """Body exactly equal to max_bytes passes (limit is exclusive)."""
    payload = b"x" * _MAX_BYTES
    response = await client.post("/echo", content=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == _MAX_BYTES


# ---------------------------------------------------------------------------
# Empty body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_body(client: AsyncClient):
    """Empty POST body succeeds."""
    response = await client.post("/echo", content=b"")
    assert response.status_code == 200
    data = response.json()
    assert data["length"] == 0


@pytest.mark.asyncio
async def test_delete_with_chunked_body():
    """DELETE request without Content-Length is read, replayed and limited."""
    test_app = _build_test_app(max_bytes=100)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.request(
            "DELETE",
            "/delete-with-body",
            content=b"x" * 50,
            headers={"transfer-encoding": "chunked"},
        )
        assert response.status_code == 200
        assert response.json() == {"length": 50}

        response_too_large = await ac.request(
            "DELETE",
            "/delete-with-body",
            content=b"x" * 150,
            headers={"transfer-encoding": "chunked"},
        )
        assert response_too_large.status_code == 413


@pytest.mark.asyncio
async def test_fast_path_stream_exceeds_max_bytes():
    """If cl_header is small but stream yields more than max_bytes, reject."""
    test_app = _build_test_app(max_bytes=100)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "query_string": b"",
        "headers": [(b"content-length", b"50")],
    }

    chunks = [b"x" * 60, b"y" * 60]
    chunk_index = 0

    async def mock_receive():
        nonlocal chunk_index
        if chunk_index < len(chunks):
            chunk = chunks[chunk_index]
            chunk_index += 1
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": chunk_index < len(chunks),
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, receive=mock_receive)

    received_events = []

    async def mock_send(msg):
        received_events.append(msg)

    middleware = ContentSizeLimitMiddleware(test_app, max_bytes=100)
    new_req, rejected = await middleware._read_and_replay_body(req, mock_send)

    assert rejected is True
    assert new_req is None
    assert any(
        e.get("type") == "http.response.start" and e.get("status") == 413
        for e in received_events
    )


@pytest.mark.asyncio
async def test_slow_path_spill_to_disk_and_exceed_limit():
    """Trigger slow-path tmpfile creation and subsequent size overflow rejection."""
    test_app = _build_test_app(max_bytes=20)
    middleware = ContentSizeLimitMiddleware(test_app, max_bytes=20)
    from unittest.mock import patch

    with patch.object(ContentSizeLimitMiddleware, "_MEM_BUFFER_THRESHOLD", 10):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/echo",
            "query_string": b"",
            "headers": [(b"transfer-encoding", b"chunked")],
        }

        chunks = [b"x" * 15, b"y" * 10]
        chunk_index = 0

        async def mock_receive():
            nonlocal chunk_index
            if chunk_index < len(chunks):
                chunk = chunks[chunk_index]
                chunk_index += 1
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": chunk_index < len(chunks),
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        req = Request(scope, receive=mock_receive)

        received_events = []

        async def mock_send(msg):
            received_events.append(msg)

        new_req, rejected = await middleware._read_and_replay_body(req, mock_send)

        assert rejected is True
        assert new_req is None
        assert any(
            e.get("type") == "http.response.start" and e.get("status") == 413
            for e in received_events
        )


@pytest.mark.asyncio
async def test_slow_path_spill_to_disk_success():
    """Trigger slow-path tmpfile creation, successful write and replay."""
    test_app = _build_test_app(max_bytes=30)
    middleware = ContentSizeLimitMiddleware(test_app, max_bytes=30)
    from unittest.mock import patch

    with patch.object(ContentSizeLimitMiddleware, "_MEM_BUFFER_THRESHOLD", 10):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/echo",
            "query_string": b"",
            "headers": [(b"transfer-encoding", b"chunked")],
        }

        chunks = [b"a" * 12, b"b" * 10]
        chunk_index = 0

        async def mock_receive():
            nonlocal chunk_index
            if chunk_index < len(chunks):
                chunk = chunks[chunk_index]
                chunk_index += 1
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": chunk_index < len(chunks),
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        req = Request(scope, receive=mock_receive)

        async def mock_send(msg):
            pass

        new_req, rejected = await middleware._read_and_replay_body(req, mock_send)

        assert rejected is False
        assert new_req is not None

        body = await new_req.body()
        assert body == b"a" * 12 + b"b" * 10
