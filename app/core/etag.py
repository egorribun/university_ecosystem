"""ETag and conditional requests (If-None-Match) middleware and utilities."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware


def compute_etag(content: bytes | str) -> str:
    """Compute ETag from response content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def format_etag(etag: str) -> str:
    """Format ETag with quotes for HTTP header."""
    if not etag:
        return etag
    etag = etag.strip()
    if etag.startswith('"') and etag.endswith('"'):
        return etag
    return f'"{etag}"'


def parse_if_none_match(header_value: str | None) -> list[str]:
    """Parse If-None-Match header into list of ETags."""
    if not header_value:
        return []
    etags = []
    for part in header_value.split(","):
        tag = part.strip()
        if tag == "*":
            etags.append("*")
        elif tag.startswith("W/"):
            tag = tag[2:].strip()
            if tag.startswith('"') and tag.endswith('"'):
                etags.append(tag[1:-1])
        elif tag.startswith('"') and tag.endswith('"'):
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

        # Read response body
        body = b""
        if hasattr(response, "body"):
            body = response.body
        elif isinstance(response, StreamingResponse):
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    body += chunk.encode()
                else:
                    body += chunk
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

        # Return response with ETag
        return Response(
            content=body,
            status_code=response.status_code,
            headers={**dict(response.headers), "ETag": formatted_etag},
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

    return JSONResponse(
        content=orjson.loads(body),
        status_code=status_code,
        headers={"ETag": formatted_etag},
    )
