"""Content size limit middleware."""

from __future__ import annotations

# MED-W19: converted from BaseHTTPMiddleware to a raw ASGI middleware so that
# `send` is a proper parameter rather than the non-standard
# request.scope["asgi"]["send"] accessor.  This also avoids BaseHTTPMiddleware's
# full-body buffering which breaks streaming responses.
from typing import Any

from starlette.requests import Request
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_413_CONTENT_TOO_LARGE,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.exceptions.handlers import asgi_json_problem
from app.core.localization import resolve_locale


class ContentSizeLimitMiddleware:
    """Reject HTTP requests whose body exceeds *max_bytes*.

    Provides defence-in-depth on top of upstream proxy limits (nginx / caddy).
    Handles both Content-Length and chunked Transfer-Encoding so attackers
    cannot bypass the check by omitting the header.

    Body replay: when the body is streamed (no Content-Length), this middleware
    buffers the chunks, enforces the limit, and then replaces the ASGI `receive`
    callable with a replay that returns the buffered body.  Without this, the
    downstream handler would receive an already-exhausted stream (empty body),
    which is a silent, hard-to-debug data-loss bug. (TD-2: audit 2026-02-24)
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = 50 * 1024 * 1024) -> None:
        """Initialise the middleware.

        Parameters
        ----------
        max_bytes:
            Upper body size limit in bytes.  Defaults to 50 MB to match the
            nginx Ingress ``proxy-body-size: "50m"`` annotation
            (k8s/ingress.yaml).  Both values MUST remain in sync — if you
            change one, update the other.
            RZ-08 (audit 2026-03-04): mismatched limits (5 MB here, 50 MB at
            Ingress) allowed requests between those sizes to bypass the fast
            Nginx gate and be rejected deep inside ASGI after fully streaming
            the body, wasting bandwidth and backend memory.
        """
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        await self._dispatch(request, send)

    async def _dispatch(self, request: Request, send: Send) -> None:
        path = request.url.path or ""
        is_ws_path = path.startswith("/ws")

        # Fast path: Content-Length declared → reject immediately, no body read.
        cl_header = request.headers.get("content-length")
        if cl_header is not None and not is_ws_path:
            try:
                cl = int(cl_header)
            except ValueError:
                locale = resolve_locale(request=request)
                # MED-W19: send is passed as a proper parameter, not via scope
                await asgi_json_problem(
                    send,
                    status_code=HTTP_400_BAD_REQUEST,
                    title_key="titles.bad_request",
                    detail_key="errors.config.invalid_content_length",
                    locale=locale,
                    instance=str(request.url),
                )
                return
            if cl > self._max_bytes:
                locale = resolve_locale(request=request)
                await asgi_json_problem(
                    send,
                    status_code=HTTP_413_CONTENT_TOO_LARGE,
                    title_key="titles.bad_request",
                    detail_key="errors.config.payload_too_large",
                    locale=locale,
                    instance=str(request.url),
                    limit=self._max_bytes // (1024 * 1024),
                )
                return

        # Slow path: chunked / unknown length — stream, accumulate, replay.
        # Extend to DELETE because RFC 9110 permits DELETE with a body, and
        # payloads without Content-Length would bypass the fast path.
        method = request.method.upper()
        has_body = method in {"POST", "PUT", "PATCH", "DELETE"} and not is_ws_path
        if has_body and cl_header is None:
            new_request, rejected = await self._read_and_replay_body(request, send)
            if rejected:
                return
            if new_request:
                request = new_request

        await self.app(request.scope, request.receive, send)

    # PERF-1: Threshold below which body is kept in RAM; beyond this it spills to
    # a temporary disk file.  100 concurrent 4.9 MB uploads without this threshold
    # would allocate ~490 MB of heap at once.  SpooledTemporaryFile transparently
    # handles the in-memory → disk transition so replay semantics are unchanged.
    _MEM_BUFFER_THRESHOLD: int = 512 * 1024  # 512 KB

    async def _read_and_replay_body(
        self, request: Request, send: Send
    ) -> tuple[Request | None, bool]:
        """Consume request body safely within limits and return an injected replay Request.

        Bodies ≤ _MEM_BUFFER_THRESHOLD bytes are kept in RAM; larger bodies spill
        to a NamedTemporaryFile so concurrent uploads don't exhaust the heap.

        Returns (new_request, rejected): if rejected is True the error response
        has already been sent via `send` and the caller must not call app.
        """
        import tempfile

        import anyio

        # PERF-006 (audit 2026-03-10): SpooledTemporaryFile() may create a real
        # temp file on disk when data exceeds max_size — a blocking open() syscall.
        # Run construction in a thread pool to keep the event loop responsive.
        _threshold = self._MEM_BUFFER_THRESHOLD
        # Fast-path for data knowing length is small (RAM only without spooled threads)
        cl_header = request.headers.get("content-length")
        if cl_header is not None and int(cl_header) <= _threshold:
            chunks: list[bytes] = []
            async for chunk in request.stream():
                chunks.append(chunk)
            body_bytes = b"".join(chunks)
            if len(body_bytes) > self._max_bytes:
                # Should not happen if cl_header exists, but keep safety parity
                await self._send_payload_error(request, send)
                return None, True
            return self._build_replay(request, body_bytes), False

        # Slow-path for chunked data or huge files
        buffer = bytearray()
        tmpfile: Any = None
        accumulated = 0
        try:
            async for chunk in request.stream():
                accumulated += len(chunk)
                if accumulated > self._max_bytes:
                    if tmpfile is not None:
                        await anyio.to_thread.run_sync(tmpfile.close)
                    await self._send_payload_error(request, send)
                    return None, True

                if tmpfile is None:
                    if accumulated <= _threshold:
                        buffer.extend(chunk)
                    else:
                        # Switch from pure RAM to temporary thread-bounded file
                        tmpfile = await anyio.to_thread.run_sync(
                            lambda: tempfile.SpooledTemporaryFile(
                                max_size=_threshold, mode="w+b"
                            )
                        )
                        await anyio.to_thread.run_sync(tmpfile.write, buffer)
                        await anyio.to_thread.run_sync(tmpfile.write, chunk)
                        buffer.clear()  # Free memory
                else:
                    await anyio.to_thread.run_sync(tmpfile.write, chunk)

            if tmpfile is None:
                body_bytes = bytes(buffer)
            else:
                await anyio.to_thread.run_sync(tmpfile.seek, 0)
                body_bytes = await anyio.to_thread.run_sync(tmpfile.read)
        finally:
            if tmpfile is not None and not tmpfile.closed:
                await anyio.to_thread.run_sync(tmpfile.close)

        async def _replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        return Request(request.scope, receive=_replay_receive), False

    def _build_replay(self, request: Request, body_bytes: bytes) -> Request:
        async def _replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        return Request(request.scope, receive=_replay_receive)

    async def _send_payload_error(self, request: Request, send: Send) -> None:
        """Send a 413 error response via the ASGI send callable."""
        locale = resolve_locale(request=request)
        # MED-W19: send is passed as a proper parameter, not via scope
        await asgi_json_problem(
            send,
            status_code=HTTP_413_CONTENT_TOO_LARGE,
            title_key="titles.bad_request",
            detail_key="errors.config.payload_too_large",
            locale=locale,
            instance=str(request.url),
            limit=self._max_bytes // (1024 * 1024),
        )
