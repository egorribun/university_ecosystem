"""Tenant context propagation middleware."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import Request
from structlog.contextvars import clear_contextvars

from app.core.logging import bind_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx

_TENANT_ID_SAFE_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"  # pragma: allowlist secret
)


class TenantContextMiddleware:
    """Populate tenant context only from gateway-signed identity headers.

    A client-supplied tenant header is only a routing hint and cannot establish
    membership. The HMAC binds user, session, and tenant before the value can
    affect database RLS or ReBAC checks.
    """

    def __init__(self, app: Any, internal_hmac_secret: str | None = None) -> None:
        self._app = app
        self._internal_hmac_secret = (internal_hmac_secret or "").encode()

    def _resolve_trusted_tenant(self, request: Request) -> str:
        raw_tenant_id = request.headers.get("x-tenant-id", "")
        sanitised = "".join(c for c in raw_tenant_id if c in _TENANT_ID_SAFE_CHARS)[:64]
        if not sanitised or not self._internal_hmac_secret:
            return ""

        try:
            uuid.UUID(sanitised)
        except ValueError:
            return ""

        user_id = request.headers.get("x-user-id", "")
        session_id = request.headers.get("x-session-id", "")
        signature = request.headers.get("x-internal-signature", "")
        if not user_id or not session_id or not signature:
            return ""

        expected = hmac.new(
            self._internal_hmac_secret,
            f"{user_id}:{session_id}:{sanitised}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return ""
        return sanitised

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
        tenant_id = self._resolve_trusted_tenant(request)

        scope.setdefault("state", {})["tenant_id"] = tenant_id
        t_token = tenant_id_ctx.set(tenant_id)
        b_token = bypass_rls_ctx.set(False)

        if tenant_id:
            bind_context(tenant_id=tenant_id)

        async def _send_with_tenant(message: Any) -> None:
            if message["type"] == "http.response.start" and tenant_id:
                headers = list(message.get("headers", []))
                headers.append((b"x-tenant-id", tenant_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, _send_with_tenant)
        finally:
            tenant_id_ctx.reset(t_token)
            bypass_rls_ctx.reset(b_token)
            clear_contextvars()
