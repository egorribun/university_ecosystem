"""Proxy init to export split middleware modules without import cycles.

The CSRF middleware needs only ``request_id_ctx`` from this package. Eagerly
importing ``setup`` here makes ``app.core.csrf`` -> ``app.core.middleware`` ->
``app.core.middleware.setup`` -> ``app.core.csrf`` circular. Keep the small,
cycle-free request-id export eager and resolve the heavier middleware exports
on demand.
"""

from __future__ import annotations

from typing import Any

from .request_id import RequestIDMiddleware, request_id_ctx

__all__ = [
    "ContentSizeLimitMiddleware",
    "RequestIDMiddleware",
    "_ensure_vary_header",
    "configure_middleware",
    "http_response_hardening",
    "request_id_ctx",
]


def __getattr__(name: str) -> Any:
    if name == "ContentSizeLimitMiddleware":
        from .content_size import ContentSizeLimitMiddleware

        return ContentSizeLimitMiddleware
    if name in {"_ensure_vary_header", "http_response_hardening"}:
        from .response_hardening import _ensure_vary_header, http_response_hardening

        return {
            "_ensure_vary_header": _ensure_vary_header,
            "http_response_hardening": http_response_hardening,
        }[name]
    if name == "configure_middleware":
        from .setup import configure_middleware

        return configure_middleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
