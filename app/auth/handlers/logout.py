"""Logout and session revocation handlers.

Extracted from auth.py for Single Responsibility Principle compliance.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from starlette import status

from app.api.deps import get_db
from app.auth.security import decode_token
from app.core.ratelimit import sensitive_route_limit
from app.models import ActiveSession
from app.services.auth.login_service import LoginService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["auth"])


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(sensitive_route_limit())],
)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Terminate the client session.

    Revokes the current session in the database and clears all
    authentication-related cookies. Also sets Clear-Site-Data header
    to ensure browser removes cached data.
    """
    raw_token = request.cookies.get("access_token_v2")
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    payload = decode_token(raw_token) if raw_token else None
    jti = payload.get("jti") if payload else None
    if jti:
        session_expires_at: datetime | None = None
        result = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session = result.scalars().first()
        if session:
            session_expires_at = session.expires_at
            now = datetime.now(UTC)
            session.revoked_at = session.revoked_at or now
            # Rotate signing key to invalidate any tokens derived from this session
            session.signing_key = secrets.token_urlsafe(32)
        # Write the fail-closed cross-service tombstone before committing the
        # database state. A partial Redis failure can then never produce a
        # durable DB revocation that edge services interpret as active.
        from app.services.auth.redis_session import RedisSessionService

        redis_service = RedisSessionService()
        try:
            await redis_service.revoke_session(jti, expires_at=session_expires_at)
        except (RedisError, RuntimeError, OSError):
            if session:
                await db.rollback()
            raise

        if session:
            await db.commit()

            from app.core.container import get_audit_service

            audit = get_audit_service()
            audit.log(
                "auth.logout.revoked",
                request,
                user_id=session.user_id,
                reason="user_initiated",
            )

    LoginService.clear_access_token_cookie(response)
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
    return {"message": "Logged out successfully"}


__all__ = ["router"]
