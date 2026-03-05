"""WebSocket auth — JWT / cookie token validation, subprotocol handling.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: authenticate WebSocket upgrade requests.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from app.core.database import async_session
from app.models.models import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.dtos import UserDTO

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

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
            except Exception as redis_exc:
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
    except Exception:
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
