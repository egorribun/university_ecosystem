from fastapi import WebSocket

from app.api.ws.auth import (
    get_user_from_cookie,
    get_user_from_ticket,
)
from app.core.logging import get_logger
from app.models import User
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

    configured = getattr(settings, "frontend_origins_list", []) or []
    return frozenset(
        origin.rstrip("/")
        for origin in configured
        if isinstance(origin, str) and origin
    )


# LOW-W19: _ALLOWED_WS_ORIGINS is intentionally computed once at import time.
# settings.frontend_origins_list is read from the environment before the first request
# and never changes at runtime, so eager evaluation is safe and avoids the
# per-request overhead of re-reading the setting.  If dynamic reconfiguration
# is ever needed, replace this with a lazy call inside authenticate_upgrade().
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

        # RZ-W14-01 (audit 2026-03-23 Wave 14): Sec-WebSocket-Protocol JWT path
        # permanently removed.  JWTs in protocol headers are written verbatim to
        # proxy access logs (nginx/Caddy), stored in Grafana Loki / ELK, and
        # visible in browser devtools — a silent credential leak.
        #
        # Supported auth methods (priority order):
        #   1. One-time upgrade ticket (?ticket=<ott>)  ← new primary path
        #   2. HttpOnly access_token_v2 cookie          ← fallback for cookie-capable clients
        #
        # Authorization: Bearer header and Sec-WebSocket-Protocol are no longer accepted.

        # 1. One-time upgrade ticket (preferred — no JWT in headers/logs)
        ticket = websocket.query_params.get("ticket")
        if ticket:
            logger.info("Attempting WS ticket auth")
            user, session_jti = await get_user_from_ticket(ticket)
            if user:
                logger.info("WS ticket auth successful: user_id=%s", user.id)
            else:
                logger.warning("WS ticket auth failed: invalid or expired ticket")

        # 2. HttpOnly cookie fallback (for cookie-capable browser clients that
        #    have not yet migrated to the ticket flow)
        if not user:
            access_token = websocket.cookies.get("access_token_v2")
            if access_token:
                logger.info("Attempting WS cookie auth")
                user, session_jti = await get_user_from_cookie(access_token)
                if user:
                    logger.info("WS cookie auth successful: user_id=%s", user.id)
                else:
                    logger.warning("WS cookie auth failed: invalid cookie")

        return (
            user,
            session_jti,
            None,
        )  # subprotocol always None — we no longer negotiate it


authenticator = WsAuthenticator()
