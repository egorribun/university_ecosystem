"""WebSocket auth — JWT / cookie token validation, subprotocol handling.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: authenticate WebSocket upgrade requests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from app.core.database import async_session
from app.core.logging import get_logger
from app.models import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.dtos import UserDTO

logger = get_logger(__name__)

try:
    import jwt as _jwt_lib

    _JWT_DECODE_ERRORS: tuple[type[Exception], ...] = (
        _jwt_lib.exceptions.DecodeError,
        _jwt_lib.exceptions.InvalidTokenError,
        _jwt_lib.exceptions.ExpiredSignatureError,
    )
except ImportError:  # pragma: no cover
    _JWT_DECODE_ERRORS = (ValueError,)


async def get_user_from_token(token: str) -> tuple[User | UserDTO | None, str | None]:
    """Validate JWT token and return the user and session identifier."""
    from app.auth.security import decode_token

    try:
        payload = decode_token(token)
        if not payload:
            return None, None

        user_id = payload.get("sub")
        session_jti = payload.get("jti")
        if not user_id:
            return None, None

        # RZ-8: Fast-path Redis JTI revocation check (O(1), beats the DB path).
        if session_jti:
            try:
                from app.deps.cache import get_cache_client

                _redis = await get_cache_client()
                if await _redis.exists(f"revoked:jti:{session_jti}"):
                    logger.debug(
                        "WebSocket: JTI %s is revoked (Redis fast-path)", session_jti
                    )
                    return None, None
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as redis_exc:  # RZ-22-01: narrowed — Redis errors
                logger.debug(
                    "WebSocket: Redis JTI check failed, falling through to DB: %s",
                    redis_exc,
                )

        async with async_session() as session:
            user_repo = UserRepository(session)
            session_repo = SessionRepository(session)

            user = await user_repo.get(uuid.UUID(user_id))
            if not user or not user.is_active:
                return None, None

            if not session_jti:
                return None, None

            active_session = await session_repo.get_by_jti(session_jti)
            if not active_session or active_session.user_id != user.id:
                return None, None

            expires_at = active_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None, None
            if active_session.revoked_at is not None:
                return None, None

            return cast("User | UserDTO", user), session_jti
    except _JWT_DECODE_ERRORS as exc:
        logger.debug("WebSocket token validation: invalid JWT — %s", type(exc).__name__)
        return None, None
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — returns None on unexpected failure (reviewed TD-27-04)
        logger.exception(
            "WebSocket token validation: unexpected infrastructure failure"
        )
        return None, None


async def get_user_from_cookie(cookie_value: str) -> tuple[User | None, str | None]:
    """Validate session cookie and return the user."""
    return cast(
        tuple[User | None, str | None],
        await get_user_from_token(cookie_value),
    )


def extract_bearer_token(header_value: str | None) -> str | None:
    """Parse `Authorization: Bearer <token>` or bare token header."""
    if not header_value:
        return None
    parts = header_value.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def extract_token_from_subprotocol(header_value: str | None) -> str | None:
    """Extract token from `Sec-WebSocket-Protocol: access_token, <JWT>` header."""
    if not header_value:
        return None
    protocols = [p.strip() for p in header_value.split(",") if p.strip()]
    for index, protocol in enumerate(protocols):
        if protocol.lower() in {"access_token", "bearer", "authorization"}:
            if index + 1 < len(protocols):
                return protocols[index + 1]
    return None


def select_subprotocol(header_value: str | None) -> str | None:
    """Select the first known WebSocket sub-protocol from the header."""
    if not header_value:
        return None
    protocols = [p.strip() for p in header_value.split(",") if p.strip()]
    for candidate in protocols:
        if candidate.lower() in {"access_token", "bearer"}:
            return candidate
    return None


async def get_user_from_ticket(ticket: str) -> tuple[User | None, str | None]:
    """Validate a one-time WS upgrade ticket and return (user, jti).

    RZ-W14-01 (audit 2026-03-23 Wave 14): atomically consumes the ticket via
    Redis GETDEL so it cannot be replayed.  The ticket was issued by
    POST /ws/ticket and stores "{user_id}:{jti}" under "ott:ws:{ticket}".

    Returns (None, None) if the ticket is missing, expired, already used,
    or if the referenced session is invalid.
    """
    from app.api.ws.ticket import TICKET_KEY_PREFIX

    try:
        # RZ-W19-07 (audit 2026-03-24 Wave 19): validate ticket is exactly 64
        # lowercase hex chars before hitting Redis. Matches Go ws-hub's
        # validateUpgradeTicket() charset check (Wave 16).
        if len(ticket) != 64 or not all(c in "0123456789abcdef" for c in ticket):
            logger.warning("WS ticket rejected: invalid format (len=%d)", len(ticket))
            return None, None

        from app.deps.cache import get_cache_client

        redis = await get_cache_client()
        # GETDEL: atomic read + delete — prevents replay of the same ticket
        raw: str | None = await redis.getdel(f"{TICKET_KEY_PREFIX}{ticket}")
        if not raw:
            logger.debug("WS ticket not found or already used: %.8s…", ticket)
            return None, None

        # Format: "{user_id}:{jti}" — split on first colon; UUIDs contain only hyphens.
        # RZ-W15-04 (audit 2026-03-23 Wave 15): Use str.find() + explicit bounds checks
        # instead of str.index() + post-split emptiness check.  Mirrors Go handlers.go:
        #   sep := strings.Index(raw, ":")
        #   if sep <= 0 || sep == len(raw)-1 { return "", error }
        # This makes the three invalid cases explicit instead of relying on exception
        # control flow from str.index():
        #   sep == -1  → no colon at all  ("useridonly")
        #   sep == 0   → empty user_id    (":jti-value")
        #   sep == last → empty jti       ("user-id:")
        sep = raw.find(":")
        if sep <= 0 or sep == len(raw) - 1:
            # RZ-W19-04 (audit 2026-03-24 Wave 19): truncate to 4 chars max to
            # prevent creating an oracle for brute-forcing valid tickets.
            # Previously %.8s could reveal most of a short ticket.
            safe_prefix = ticket[:4] if len(ticket) > 4 else "***"
            logger.warning(
                "WS ticket has malformed payload (sep=%d len=%d): %s…",
                sep,
                len(raw),
                safe_prefix,
            )
            return None, None

        user_id_str = raw[:sep]
        jti = raw[sep + 1 :]

    except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — ticket validation failure returns None (reviewed TD-27-04)
        logger.warning("WS ticket validation error: %s", exc)
        return None, None

    # Validate session via direct DB lookup (no JWT decode needed — we already
    # verified the caller's identity when the ticket was issued).
    return await _resolve_user_from_ids(user_id_str, jti)


async def _resolve_user_from_ids(
    user_id_str: str, jti: str
) -> tuple[User | None, str | None]:
    """Look up user + validate session directly from user_id + jti.

    Shared by get_user_from_ticket() — avoids re-encoding a fake JWT.
    """
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            session_repo = SessionRepository(session)

            user = await user_repo.get(uuid.UUID(user_id_str))
            if not user or not user.is_active:
                return None, None

            # Fast-path Redis revocation check
            try:
                from app.deps.cache import get_cache_client as _gcc

                _redis = await _gcc()
                if await _redis.exists(f"revoked:jti:{jti}"):
                    logger.debug("WS ticket JTI %s is revoked (Redis fast-path)", jti)
                    return None, None
            except ConnectionError, TimeoutError, OSError:  # nosec B110  # RZ-28-01 + RZ-22-01: narrowed — Redis errors
                pass  # fallback to DB revoked_at check below

            active_session = await session_repo.get_by_jti(jti)
            if not active_session or active_session.user_id != user.id:
                return None, None

            expires_at = active_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                return None, None
            if active_session.revoked_at is not None:
                return None, None

            return cast("User | None", user), jti

    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — user resolution failure returns None (reviewed TD-27-04)
        logger.exception("WS ticket: unexpected error resolving user")
        return None, None


async def update_last_seen(session_jti: str | None) -> datetime:
    """Persist last_seen_at for a session and return the timestamp used."""
    now = datetime.now(UTC)
    if not session_jti:
        return now

    async with async_session() as session:
        repo = SessionRepository(session)
        await repo.touch_by_jti(session_jti)
        await session.commit()

    return now
