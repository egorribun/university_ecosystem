import logging

from app.core.logging import get_logger

from fastapi import WebSocket

from app.api.ws.auth import (
    extract_bearer_token,
    extract_token_from_subprotocol,
    get_user_from_cookie,
    get_user_from_token,
    select_subprotocol,
)
from app.models.models import User
from app.schemas.dtos import UserDTO

logger = get_logger(__name__)


def _get_allowed_ws_origins() -> frozenset[str]:
    """Build the set of allowed WebSocket upgrade origins.

    R-03 (audit 2026-03-08): Origin validation prevents Cross-Site WebSocket
    Hijacking (CSWSH).  Returns an empty frozenset in dev/test environments so
    the check is skipped entirely — avoids breaking local development where
    frontend and API run on different ports.
    """
    from app.core.config import settings

    raw = getattr(settings, "frontend_url", "") or ""
    origin = raw.rstrip("/")
    return frozenset([origin]) if origin else frozenset()


_ALLOWED_WS_ORIGINS: frozenset[str] = _get_allowed_ws_origins()


class WsAuthenticator:
    """Handles authentication for WebSocket upgrade requests."""

    async def authenticate_upgrade(
        self, websocket: WebSocket
    ) -> tuple[User | UserDTO | None, str | None, str | None]:
        # R-03 (audit 2026-03-08): Origin validation — reject cross-origin WS
        # upgrades before any token processing.  _ALLOWED_WS_ORIGINS is empty in
        # dev/test so the check is skipped entirely there.
        origin = websocket.headers.get("origin")
        if _ALLOWED_WS_ORIGINS and origin and origin not in _ALLOWED_WS_ORIGINS:
            logger.warning(
                "WebSocket upgrade rejected: invalid Origin %r (allowed: %s)",
                origin,
                _ALLOWED_WS_ORIGINS,
            )
            await websocket.close(code=1008)  # 1008 = Policy Violation
            return None, None, None

        user = None
        session_jti = None

        auth_header = websocket.headers.get("authorization")
        protocol_header = websocket.headers.get("sec-websocket-protocol")
        header_token = extract_bearer_token(auth_header)
        protocol_token = extract_token_from_subprotocol(protocol_header)
        selected_subprotocol = select_subprotocol(protocol_header)

        if header_token or protocol_token:
            logger.info(
                "Attempting WebSocket token auth from headers (auth=%s, protocol=%s)",
                bool(header_token),
                bool(protocol_token),
            )
            token_str = str(header_token or protocol_token)
            user, session_jti = await get_user_from_token(token_str)
            if user:
                logger.info("Token auth successful: user_id=%s", user.id)
            else:
                logger.warning("Token auth failed: invalid token")

        # R-07 (audit 2026-03-08): Query param token auth permanently removed.
        # Tokens in URL parameters are logged by Nginx/Caddy in plaintext, cached
        # by browsers and proxies, and leak via Referer headers.
        # Supported auth methods: Authorization: Bearer header, Sec-WebSocket-Protocol
        # subprotocol token (Go ws-hub), HttpOnly access_token_v2 cookie.

        if not user:
            access_token = websocket.cookies.get("access_token_v2")
            if access_token:
                logger.info("Attempting cookie auth, access_token present: True")
                user, session_jti = await get_user_from_cookie(access_token)
                if user:
                    logger.info("Cookie auth successful: user_id=%s", user.id)
                else:
                    logger.warning("Cookie auth failed: invalid cookie")

        return user, session_jti, selected_subprotocol


authenticator = WsAuthenticator()
