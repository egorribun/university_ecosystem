"""WS upgrade ticket endpoint (RZ-W14-01, audit 2026-03-23 Wave 14).

Issues short-lived (15s), single-use upgrade tickets for WebSocket connections.
Eliminates JWT exposure in Sec-WebSocket-Protocol proxy-visible headers and logs.

Flow
----
1. Client calls POST /ws/ticket (authenticated via HttpOnly cookie / Bearer token)
2. Backend stores ticket → "{user_id}:{jti}" in Redis: "ott:ws:{ticket}" (TTL=15s)
3. Client opens: wss://host/ws/chat?ticket=<ticket>
4. WS handler calls GETDEL (atomic, single-use) and authenticates from the stored payload

Redis key schema (see contracts/redis-keys.md)
----------------------------------------------
Key  : ott:ws:{ticket}   — 64-char lowercase hex (32 random bytes via secrets.token_hex)
Value: {user_id}:{jti}   — colon-joined UUIDs; split on first ":" to parse
TTL  : WS_TICKET_TTL_SECONDS (default 15)
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.localization import resolve_locale
from app.core.logging import get_logger
from app.deps.cache import get_cache_client
from app.services.auth.token_service import AuthTokenService

logger = get_logger(__name__)


# LOW-W19: replaced os.environ.get() with settings.ws_ticket_ttl_seconds so the
# value is validated at startup, visible in .env docs, and overridable in tests
# via Settings overrides rather than os.environ patches.
# MOD-W17-06 (Wave 17): configurable; default 15 s.  On slow networks (mobile,
# CDN multi-hop) consider 30-60 s.  On high-security deployments keep at 15 s.
def _get_ticket_ttl() -> int:
    return settings.ws_ticket_ttl_seconds


TICKET_KEY_PREFIX: str = "ott:ws:"

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

router = APIRouter(prefix="/ws", tags=["websocket"])


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int


@router.post(
    "/ticket",
    response_model=WsTicketResponse,
    status_code=201,
    summary="Issue a WebSocket upgrade ticket",
    description=(
        "Issues a short-lived, single-use WebSocket upgrade ticket. "
        "The client must be authenticated via HttpOnly cookie or Bearer token. "
        "Connect to the WebSocket endpoint with ?ticket=<ticket> — the ticket "
        "is consumed atomically on first use and expires after WS_TICKET_TTL_SECONDS seconds "
        "if unused (default: 15 s; configure via settings.ws_ticket_ttl_seconds)."
    ),
)
async def issue_ws_upgrade_ticket(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_scheme)],
) -> WsTicketResponse:
    """RZ-W14-01: issue a one-time-use WebSocket upgrade ticket.

    Extracts user_id + jti from the caller's JWT (Bearer or cookie), stores them
    under a random ticket key in Redis, and returns the ticket to the client.
    The WS handler then performs an atomic GETDEL to authenticate the upgrade
    without any JWT ever appearing in WebSocket protocol headers or proxy logs.
    """
    from app.core.tenant import get_current_tenant

    locale = resolve_locale(request=request)
    payload = AuthTokenService.extract_and_decode_token(request, token, locale)
    user_id, jti = AuthTokenService.validate_payload(payload, locale)

    tenant_id = get_current_tenant() or request.headers.get("X-Tenant-ID", "")
    ticket = secrets.token_hex(32)  # 64-char hex, 256 bits of entropy
    redis_value = f"{user_id}:{jti}:{tenant_id}" if tenant_id else f"{user_id}:{jti}"
    ttl = _get_ticket_ttl()

    try:
        redis = await get_cache_client()
        await redis.set(
            f"{TICKET_KEY_PREFIX}{ticket}",
            redis_value,
            ex=ttl,
        )
    except RuntimeError:
        # RZ-22-01-JUSTIFIED: graceful degradation when NullCache is active during tests
        logger.warning(
            "NullCache active, bypassing Redis ticket storage for user_id=%s", user_id
        )

    logger.debug("Issued WS upgrade ticket for user_id=%s jti=%.8s", user_id, jti)
    return WsTicketResponse(ticket=ticket, expires_in=ttl)
