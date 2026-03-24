"""Custom HTTP Response Hardening."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request
from starlette.responses import Response


def _ensure_vary_header(response: Response, header_name: str) -> None:
    # PERF-14-02 (audit Wave 14): Use a set for O(1) membership check instead
    # of the previous list + linear scan.  Called 1-3 times per response with
    # CORS, so the micro-optimisation accumulates across all HTTP traffic.
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = header_name
        return
    values = {v.strip() for v in existing.split(",")}
    if header_name not in values:
        values.add(header_name)
        response.headers["Vary"] = ", ".join(sorted(values))


async def http_response_hardening(
    request: Request, call_next: Callable[[Request], Coroutine[Any, Any, Response]]
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        # Encourage browsers to keep avatars locally without marking them immutable.
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    # TD-21-07 (audit 2026-03-25 Wave 21): Signal API v1 sunset to consumers.
    # The Deprecation/Sunset headers follow RFC 8594 and RFC 8288.
    # Clients that parse these headers can warn operators and start migration.
    if request.url.path.startswith("/api/v1"):
        response.headers.setdefault("Deprecation", "true")
        response.headers.setdefault("Sunset", "2026-12-31T00:00:00Z")
        response.headers.setdefault("Link", '</api/v2>; rel="successor-version"')

    acao = response.headers.get("access-control-allow-origin")
    if acao and acao != "*":
        _ensure_vary_header(response, "Origin")
        if request.method.upper() == "OPTIONS":
            _ensure_vary_header(response, "Access-Control-Request-Method")
            if request.headers.get("access-control-request-headers"):
                _ensure_vary_header(response, "Access-Control-Request-Headers")
    return response
