"""ETag and conditional requests (If-None-Match) middleware and utilities."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware


def compute_etag(content: bytes | str) -> str:
    """Compute ETag from response content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    # LOW-W19: Truncate SHA-256 digest to 32 hex chars (128 bits of entropy).
    # The full 64-char hex provides no practical collision-resistance benefit
    # for ETags; 32 chars are more than sufficient and halve header size.
    return hashlib.sha256(content).hexdigest()[:32]


def format_etag(etag: str) -> str:
    """Format ETag with quotes for HTTP header."""
    if not etag:
        return etag
    etag = etag.strip()
    if etag.startswith('"') and etag.endswith('"'):
        return etag
    return f'"{etag}"'


def parse_if_none_match(header_value: str | None) -> list[str]:
    """Parse If-None-Match header into list of ETags.

    Per RFC 7232 §2.3, If-None-Match uses *weak* comparison: a weak ETag
    (W/"<opaque-tag>") matches a strong ETag with the same opaque-tag value.
    We therefore strip the ``W/`` prefix and add the bare opaque value so that
    ``etag_matches()`` can compare it against the strong ETag we generate.

    LOW-W19: Previous code silently dropped weak ETags whose quoted value was
    not immediately adjacent to ``W/`` (e.g. ``W/ "abc"``).  The strip() call
    now handles optional whitespace between ``W/`` and the quoted string, as
    permitted by RFC 7230 list rules.
    """
    if not header_value:
        return []
    etags = []
    for part in header_value.split(","):
        tag = part.strip()
        if tag == "*":
            etags.append("*")
        elif tag.upper().startswith("W/"):
            # LOW-W19: RFC 7232 §2.1 — strip W/ prefix and optional whitespace,
            # then extract the opaque-tag from the surrounding quotes so it can
            # be compared with the strong ETag value we produce.
            inner = tag[2:].strip()
            if inner.startswith('"') and inner.endswith('"') and len(inner) >= 2:
                etags.append(inner[1:-1])
        elif tag.startswith('"') and tag.endswith('"') and len(tag) >= 2:
            etags.append(tag[1:-1])
    return etags


def etag_matches(etag: str, if_none_match: list[str]) -> bool:
    """Check if ETag matches any value in If-None-Match list."""
    if not etag or not if_none_match:
        return False
    if "*" in if_none_match:
        return True
    return etag in if_none_match


class ETagMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds ETag headers and handles If-None-Match.

    Returns 304 Not Modified when the client's cached version matches.
    Only applies to GET requests with successful responses.
    """

    def __init__(
        self,
        app: Any,
        skip_paths: tuple[str, ...] = ("/healthz", "/metrics", "/ws"),
    ) -> None:
        super().__init__(app)
        self.skip_paths = skip_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Only apply to GET requests
        if request.method != "GET":
            return await call_next(request)

        # Skip certain paths
        if any(request.url.path.startswith(p) for p in self.skip_paths):
            return await call_next(request)

        response = await call_next(request)

        # Only process successful JSON responses
        if response.status_code != 200:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # PERF-W19-09: skip ETag computation for StreamingResponse to avoid
        # buffering the entire stream in memory.
        if isinstance(response, StreamingResponse):
            return response

        # Read response body
        body = b""
        if hasattr(response, "body"):
            body = cast(Any, response).body
        else:
            return response

        # Compute ETag
        etag = compute_etag(body)
        formatted_etag = format_etag(etag)

        # Check If-None-Match header
        if_none_match_header = request.headers.get("if-none-match")
        if_none_match = parse_if_none_match(if_none_match_header)

        if etag_matches(etag, if_none_match):
            # Return 304 Not Modified
            return Response(
                status_code=304,
                headers={"ETag": formatted_etag},
            )

        # Return response with ETag — use items() to preserve duplicate headers
        merged_headers = dict(response.headers.items())
        merged_headers["ETag"] = formatted_etag
        return Response(
            content=body,
            status_code=response.status_code,
            headers=merged_headers,
            media_type=response.media_type,
        )


def conditional_response(
    request: Request,
    content: Any,
    status_code: int = 200,
) -> Response:
    """
    Create a response with ETag support.

    If the client provides matching If-None-Match, returns 304.
    Otherwise returns the content with ETag header.

    Args:
        request: FastAPI request object
        content: Response content (will be JSON serialized)
        status_code: HTTP status code for successful response

    Returns:
        JSONResponse or 304 Response
    """
    import orjson

    body = orjson.dumps(content)
    etag = compute_etag(body)
    formatted_etag = format_etag(etag)

    if_none_match_header = request.headers.get("if-none-match")
    if_none_match = parse_if_none_match(if_none_match_header)

    if etag_matches(etag, if_none_match):
        return Response(
            status_code=304,
            headers={"ETag": formatted_etag},
        )

    # LOW-W19: Return pre-serialised bytes directly instead of passing the
    # Python object to JSONResponse, which would call json.dumps() a second
    # time (double serialization).  Using Response with the raw bytes and the
    # correct media_type avoids the redundant encode/decode round-trip.
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/json",
        headers={"ETag": formatted_etag},
    )
