"""Request ID injection middleware."""

from __future__ import annotations

import uuid as _uuid_module
from contextvars import ContextVar
from typing import Any

from fastapi import Request

from app.core.logging import bind_context

# D-04 (audit 2026-03-08): Correlation ID available to any logger in this process
# via request_id_ctx.get().  Set by RequestIDMiddleware on every HTTP request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

_REQUEST_ID_SAFE_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"  # pragma: allowlist secret
)


class RequestIDMiddleware:
    """Inject X-Request-ID into request scope and response headers.

    Accepts a client-supplied ``X-Request-ID`` header (useful for distributed
    tracing across services) or generates a fresh UUID4 when absent.

    The value is:
    - sanitised (only alphanum + ``-`` ``_``, max 64 chars) to prevent header
      injection via a crafted client header;
    - stored in ``request.state.request_id`` for use in route handlers;
    - propagated to loggers via the ``request_id_ctx`` ContextVar;
    - echoed back in the ``X-Request-ID`` response header so callers can
      correlate logs across FastAPI, ws-hub, and file-processor.

    Implemented as a raw ASGI callable (not BaseHTTPMiddleware) so streaming
    responses (SSE, NDJSON) are never buffered.  (D-04: audit 2026-03-08)
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        raw_id = request.headers.get("x-request-id", "")
        # Sanitise: keep only safe characters, truncate to 64, fall back to UUID4
        sanitised = "".join(c for c in raw_id if c in _REQUEST_ID_SAFE_CHARS)[:64]
        request_id = sanitised or str(_uuid_module.uuid4())

        scope.setdefault("state", {})["request_id"] = request_id
        ctx_token = request_id_ctx.set(request_id)
        # Binds request_id to the current asyncio task context for structlog.
        bind_context(request_id=request_id)

        async def _send_with_id(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, _send_with_id)
        finally:
            request_id_ctx.reset(ctx_token)
