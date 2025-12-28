"""
Sanitization middleware for FastAPI.

Provides middleware that sanitizes incoming JSON request bodies
to prevent XSS and injection attacks at the request level.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.sanitization import sanitize_html, strip_control_chars

logger = logging.getLogger(__name__)


class SanitizationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that sanitizes string values in JSON request bodies.

    This provides defense-in-depth by sanitizing input at the request level,
    in addition to Pydantic validators on individual fields.

    Args:
        app: The ASGI application
        enabled: Whether sanitization is enabled
        sanitize_html_fields: If True, HTML-escape string values
        strip_control_chars: If True, remove control characters
        skip_paths: Paths to skip sanitization (e.g., admin endpoints)
        max_depth: Maximum recursion depth for nested objects
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool = True,
        sanitize_html_fields: bool = True,
        strip_control_chars_enabled: bool = True,
        skip_paths: tuple[str, ...] = ("/api/internal/",),
        max_depth: int = 10,
    ) -> None:
        super().__init__(app)
        self._enabled = enabled
        self._sanitize_html = sanitize_html_fields
        self._strip_control = strip_control_chars_enabled
        self._skip_paths = skip_paths
        self._max_depth = max_depth

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._enabled:
            return await call_next(request)

        # Skip for non-mutating methods
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # Skip certain paths
        path = request.url.path
        if any(path.startswith(skip) for skip in self._skip_paths):
            return await call_next(request)

        # Only process JSON content
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return await call_next(request)

        # Read and sanitize body
        try:
            body = await request.body()
            if not body:
                return await call_next(request)

            data = json.loads(body)
            sanitized = self._sanitize_value(data, depth=0)
            sanitized_body = json.dumps(sanitized).encode("utf-8")

            # Create new request with sanitized body
            request._body = sanitized_body

        except json.JSONDecodeError:
            # Let the actual handler deal with invalid JSON
            pass
        except Exception as e:
            logger.warning("Sanitization middleware error: %s", e)

        return await call_next(request)

    def _sanitize_value(self, value: Any, depth: int) -> Any:
        """Recursively sanitize values in a data structure."""
        if depth > self._max_depth:
            return value

        if isinstance(value, str):
            result = value
            if self._strip_control:
                result = strip_control_chars(result)
            if self._sanitize_html:
                result = sanitize_html(result, allow_basic_tags=False)
            return result

        if isinstance(value, dict):
            return {k: self._sanitize_value(v, depth + 1) for k, v in value.items()}

        if isinstance(value, list):
            return [self._sanitize_value(item, depth + 1) for item in value]

        # Non-string primitives pass through unchanged
        return value


def create_sanitization_middleware(
    *,
    enabled: bool = True,
    skip_paths: tuple[str, ...] = ("/api/internal/",),
) -> type[SanitizationMiddleware]:
    """
    Factory function to create configured sanitization middleware.

    Usage:
        app.add_middleware(create_sanitization_middleware(enabled=True))
    """

    class ConfiguredMiddleware(SanitizationMiddleware):
        def __init__(self, app: ASGIApp) -> None:
            super().__init__(app, enabled=enabled, skip_paths=skip_paths)

    return ConfiguredMiddleware


__all__ = ["SanitizationMiddleware", "create_sanitization_middleware"]
