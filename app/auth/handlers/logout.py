"""Logout and session revocation handlers.

Extracted from auth.py for Single Responsibility Principle compliance.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_db
from app.auth.security import decode_token
from app.models.models import ActiveSession
from app.services.auth.login_service import LoginService

router = APIRouter(tags=["auth"])


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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
        result = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session = result.scalars().first()
        if session:
            now = datetime.now(UTC)
            session.revoked_at = session.revoked_at or now
            # Rotate signing key to invalidate any tokens derived from this session
            session.signing_key = secrets.token_urlsafe(32)
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
