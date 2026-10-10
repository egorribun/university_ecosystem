"""WebSocket auth — JWT / cookie token validation, subprotocol handling.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: authenticate WebSocket upgrade requests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from redis.exceptions import RedisError

from app.auth.revocation import get_revocation_redis_client
from app.core.database import async_session
from app.core.logging import get_logger
from app.models import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.dtos import UserDTO
from app.services.auth.session_policy import session_is_usable

logger = get_logger(__name__)

try:
    import jwt as _jwt_lib

    _JWT_DECODE_ERRORS: tuple[type[Exception], ...] = (
        _jwt_lib.exceptions.DecodeError,
        _jwt_lib.exceptions.InvalidTokenError,
        _jwt_lib.exceptions.ExpiredSignatureError,
    )
except ImportError:
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

        # Durable revocation is mandatory. The DB row may remain active after a
        # tombstone-first mutation rolls back, so it cannot replace this check.
        if session_jti:
            try:
                _redis = await get_revocation_redis_client()
                if await _redis.exists(f"revoked:jti:{session_jti}"):
                    logger.debug(
                        "WebSocket session rejected by durable revocation state"
                    )
                    return None, None
            except (RedisError, RuntimeError, OSError):
                logger.warning("WebSocket session revocation verification unavailable")
                return None, None

        async with async_session() as session:
            user_repo = UserRepository(session)
            session_repo = SessionRepository(session)

            user = await user_repo.get(uuid.UUID(user_id))
            if not user or not user.is_active:
                return None, None

            if not session_jti:
                return None, None

            active_session = await session_repo.get_by_jti(session_jti)
            if active_session is None or not session_is_usable(active_session, user):
                return None, None

            return cast("User | UserDTO", user), session_jti
    except _JWT_DECODE_ERRORS as exc:
        logger.debug("websocket.jwt_rejected", error_type=type(exc).__name__)
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


async def get_user_from_ticket(ticket: str) -> tuple[User | None, str | None]:
    """Validate a one-time WS upgrade ticket and return (user, jti).

    RZ-W14-01 (audit 2026-03-23 Wave 14): atomically consumes the ticket via
    Redis GETDEL so it cannot be replayed.  The ticket was issued by
    POST /ws/ticket stores "{user_id}:{jti}:{expires_at_unix_seconds}"
    under "ott:ws:{ticket}".

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
        raw: str | bytes | None = await redis.getdel(f"{TICKET_KEY_PREFIX}{ticket}")
        if not raw:
            logger.debug("WS ticket not found or already used: %.8s…", ticket)
            return None, None

        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        # Reject legacy two-field tickets and any alternate expiry encoding.
        # Match Go's positive signed-int64 decimal contract without accepting
        # whitespace, a sign, Unicode digits, fractions, or leading zeroes.
        parts = raw.split(":")
        if (
            len(parts) != 3
            or not parts[0]
            or not parts[1]
            or not 1 <= len(parts[2]) <= 19
            or parts[2][0] not in "123456789"
            or any(char not in "0123456789" for char in parts[2])
        ):
            # RZ-W19-04 (audit 2026-03-24 Wave 19): truncate to 4 chars max to
            # prevent creating an oracle for brute-forcing valid tickets.
            # Previously %.8s could reveal most of a short ticket.
            safe_prefix = ticket[:4] if len(ticket) > 4 else "***"
            logger.warning(
                "WS ticket has malformed payload (sep=%d len=%d): %s…",
                raw.find(":"),
                len(raw),
                safe_prefix,
            )
            return None, None

        user_id_str, jti, expiry_text = parts
        expires_at_seconds = int(expiry_text)
        if (
            expires_at_seconds > 2**63 - 1
            or expires_at_seconds <= datetime.now(UTC).timestamp()
        ):
            return None, None

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
    # The one-time ticket is consumed before reaching this resolver. Check the
    # mandatory durable tombstone before opening a DB session: after a failed
    # security transaction the DB row can still be active while the tombstone
    # correctly rejects the credential.
    try:
        _redis = await get_revocation_redis_client()
        if await _redis.exists(f"revoked:jti:{jti}"):
            logger.debug(
                "WebSocket ticket session rejected by durable revocation state"
            )
            return None, None
    except (RedisError, RuntimeError, OSError):
        logger.warning("WebSocket ticket revocation verification unavailable")
        return None, None

    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            session_repo = SessionRepository(session)

            user = await user_repo.get(uuid.UUID(user_id_str))
            if not user or not user.is_active:
                return None, None

            active_session = await session_repo.get_by_jti(jti)
            if active_session is None or not session_is_usable(active_session, user):
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
