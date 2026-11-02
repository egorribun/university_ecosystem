"""Tenant context propagation middleware."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
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

    def __init__(
        self,
        app: Any,
        internal_hmac_secret: str | None = None,
        mvp_tenant_id: uuid.UUID | None = None,
    ) -> None:
        self._app = app
        self._mvp_tenant_id = str(mvp_tenant_id) if mvp_tenant_id else ""
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
        if (
            not user_id
            or not session_id
            or len(signature) != 64
            or not signature.isascii()
        ):
            return ""

        expected = hmac.new(
            self._internal_hmac_secret,
            f"{user_id}:{session_id}:{sanitised}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return ""
        return sanitised

    def _accept_mvp_identity(self, request: Request, trusted_tenant: str) -> bool:
        """Never downgrade an invalid supplied identity to anonymous routing."""
        identity_headers = ("x-user-id", "x-session-id", "x-internal-signature")
        if any(name in request.headers for name in identity_headers):
            return trusted_tenant == self._mvp_tenant_id
        authorization = request.headers.get("authorization")
        cookie = request.cookies.get("access_token_v2")
        if authorization is None and cookie is None:
            # A raw X-Tenant-ID is only an untrusted hint and is ignored.
            return True
        token = None
        if authorization is not None:
            # This exact endpoint owns a distinct Basic-auth service principal.
            # Its handler still verifies credentials and the source allowlist;
            # no user/session identity is inferred and no other path is exempt.
            if (
                request.method == "GET"
                and request.url.path == "/metrics"
                and authorization.startswith("Basic ")
            ):
                return True
            scheme, separator, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not separator or not token.strip():
                return False
            token = token.strip()
        from app.services.auth.token_service import AuthTokenService

        try:
            payload = AuthTokenService.extract_and_decode_token(request, token, "en")
            AuthTokenService.validate_payload(payload, "en")
        except HTTPException:
            return False
        return payload.get("tenant_id") == self._mvp_tenant_id

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Bind an upgrade to the MVP tenant before the WebSocket handler runs.

        An upgrade has no client tenant header, so the HttpOnly access cookie is the
        only tenant evidence. A cookie from another tenant, or one that does not
        decode, is refused before the handshake (close 1008). Ticket upgrades were
        issued under the HTTP tenant gate and bind to the configured tenant here.
        Without a configured tenant the scope passes through unchanged.
        """
        if not self._mvp_tenant_id:
            await self._app(scope, receive, send)
            return
        cookie = HTTPConnection(scope).cookies.get("access_token_v2")
        if cookie is not None and not self._cookie_in_mvp_tenant(cookie):
            await send({"type": "websocket.close", "code": 1008})
            return
        scope.setdefault("state", {})["tenant_id"] = self._mvp_tenant_id
        t_token = tenant_id_ctx.set(self._mvp_tenant_id)
        b_token = bypass_rls_ctx.set(False)
        try:
            await self._app(scope, receive, send)
        finally:
            tenant_id_ctx.reset(t_token)
            bypass_rls_ctx.reset(b_token)

    def _cookie_in_mvp_tenant(self, token: str) -> bool:
        from app.auth.security import decode_token

        payload = decode_token(token)
        return payload is not None and payload.get("tenant_id") == self._mvp_tenant_id

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        tenant_id = self._resolve_trusted_tenant(request)
        if self._mvp_tenant_id:
            if not self._accept_mvp_identity(request, tenant_id):
                response = JSONResponse(
                    {"detail": "credentials_invalid"}, status_code=401
                )
                if "access_token_v2" in request.cookies:
                    response.delete_cookie("access_token_v2", path="/")
                await response(scope, receive, send)
                return
            # Only absent credentials bootstrap through operator authority.
            # Present identity must already bind to this organization; normal
            # auth dependencies still check durable sessions and revocation.
            tenant_id = self._mvp_tenant_id

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
