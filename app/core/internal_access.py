from __future__ import annotations

import logging

from app.core.logging import get_logger
import secrets
from typing import TYPE_CHECKING, Any

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence

    from starlette.requests import Request

_logger = get_logger(__name__)


class InternalAccessMiddleware(BaseHTTPMiddleware):
    """Restrict access to internal routes by header token or client IP."""

    def __init__(
        self,
        app: Any,
        *,
        allowed_ips: Iterable[str] = (),
        header_name: str | None = None,
        header_token: str | None = None,
        internal_prefixes: Sequence[str] = (),
    ) -> None:
        super().__init__(app)
        self.allowed_ips = {ip.strip() for ip in allowed_ips if ip and ip.strip()}
        self.header_name = header_name
        self.header_token = header_token
        self.internal_prefixes = tuple(
            prefix.rstrip("/") for prefix in internal_prefixes
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if not any(path.startswith(prefix) for prefix in self.internal_prefixes):
            return await call_next(request)

        # 1. Check for Token (Primary & Required in Prod)
        if self._has_valid_header(request):
            response = await call_next(request)
            self._ensure_vary_header(response)
            return response

        # 2. Check for IP (Secondary / Legacy)
        if self._is_allowed_ip(request):
            # IP-only access is a fallback path — always audit it so operators
            # know it is being exercised and can migrate callers to token auth.
            client_ip = request.client.host if request.client else "unknown"
            _logger.warning(
                "Internal API accessed via IP-only allowlist (no token). "
                "Migrate caller to header-token authentication. "
                "ip=%s path=%s method=%s",
                client_ip,
                path,
                request.method,
            )
            return await call_next(request)

        # 3. Deny if neither matches
        _logger.warning(
            "Internal API access denied for %s at %s. No valid token provided.",
            request.client.host if request.client else "unknown",
            path,
        )

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Internal API access denied"},
        )

    def _is_allowed_ip(self, request: Request) -> bool:
        if not self.allowed_ips:
            return False
        client = request.client
        if not client:
            return False
        return client.host in self.allowed_ips

    def _has_valid_header(self, request: Request) -> bool:
        if not self.header_name or not self.header_token:
            return False
        provided = request.headers.get(self.header_name)
        if not provided:
            return False
        return secrets.compare_digest(provided, self.header_token)

    def _ensure_vary_header(self, response: Response) -> None:
        if not self.header_name:
            return
        existing = response.headers.get("Vary")
        if not existing:
            response.headers["Vary"] = self.header_name
            return
        values = [value.strip() for value in existing.split(",") if value.strip()]
        if self.header_name not in values:
            values.append(self.header_name)
            response.headers["Vary"] = ", ".join(values)
