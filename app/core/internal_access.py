from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from fastapi import status
from starlette.responses import JSONResponse

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from starlette.types import Receive, Scope, Send

_logger = get_logger(__name__)


# MED-W19: converted from BaseHTTPMiddleware to a raw ASGI middleware class to
# avoid BaseHTTPMiddleware's full-body buffering, which prevents streaming
# responses from reaching the client incrementally.
class InternalAccessMiddleware:
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
        self.app = app
        self.allowed_ips = {ip.strip() for ip in allowed_ips if ip and ip.strip()}
        self.header_name = header_name
        self.header_token = header_token
        self.internal_prefixes = tuple(
            prefix.rstrip("/") for prefix in internal_prefixes
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "") or "/"
        path = path.rstrip("/") or "/"

        if not any(path.startswith(prefix) for prefix in self.internal_prefixes):
            await self.app(scope, receive, send)
            return

        # Build a minimal Request-like view from scope for header/IP checks
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        client = scope.get("client")
        client_host: str = client[0] if client else "unknown"

        # 1. Check for Token (Primary & Required in Prod)
        if self._has_valid_header_from_scope(headers):
            vary_send = self._make_vary_send(send)
            await self.app(scope, receive, vary_send)
            return

        # 2. Check for IP (Secondary / Legacy)
        if self._is_allowed_ip_from_scope(client_host):
            _logger.warning(
                "Internal API accessed via IP-only allowlist (no token). "
                "Migrate caller to header-token authentication. "
                "ip=%s path=%s method=%s",
                client_host,
                path,
                scope.get("method", ""),
            )
            await self.app(scope, receive, send)
            return

        # 3. Deny if neither matches
        _logger.warning(
            "Internal API access denied for %s at %s. No valid token provided.",
            client_host,
            path,
        )
        response = JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Internal API access denied"},
        )
        await response(scope, receive, send)

    def _is_allowed_ip_from_scope(self, client_host: str) -> bool:
        if not self.allowed_ips:
            return False
        return client_host in self.allowed_ips

    def _has_valid_header_from_scope(self, headers: dict[bytes, bytes]) -> bool:
        if not self.header_name or not self.header_token:
            return False
        provided_bytes = headers.get(self.header_name.lower().encode())
        if not provided_bytes:
            return False
        try:
            provided = provided_bytes.decode("latin-1")
        except Exception:
            return False
        return secrets.compare_digest(provided, self.header_token)

    def _make_vary_send(self, send: Send) -> Send:
        """Return a wrapped send that injects Vary: <header_name> on responses."""
        if not self.header_name:
            return send

        header_name = self.header_name

        async def _vary_send(message: Any) -> None:
            if message.get("type") == "http.response.start":
                raw_headers: list[tuple[bytes, bytes]] = list(
                    message.get("headers", [])
                )
                vary_key = b"vary"
                existing_vary: bytes | None = None
                remaining: list[tuple[bytes, bytes]] = []
                for k, v in raw_headers:
                    if k.lower() == vary_key:
                        existing_vary = v
                    else:
                        remaining.append((k, v))

                if existing_vary is None:
                    new_vary = header_name.encode("latin-1")
                else:
                    values = [
                        s.strip()
                        for s in existing_vary.decode("latin-1").split(",")
                        if s.strip()
                    ]
                    if header_name not in values:
                        values.append(header_name)
                    new_vary = ", ".join(values).encode("latin-1")

                remaining.append((vary_key, new_vary))
                message = {**message, "headers": remaining}
            await send(message)

        return _vary_send
