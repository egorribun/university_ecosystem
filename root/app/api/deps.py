from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.core.database import get_db
from app.localization import resolve_locale, translate
from app.models.models import ActiveSession, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    locale = resolve_locale(request=request)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=translate("errors.auth.credentials_invalid", locale=locale),
        headers={"WWW-Authenticate": "Bearer"},
    )
    raw_token = token or request.cookies.get("access_token")
    if not raw_token:
        raise credentials_exception
    payload = decode_token(raw_token)
    if not payload:
        raise credentials_exception
    sub = payload.get("sub")
    jti = payload.get("jti")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise credentials_exception
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exception
    if not jti:
        raise credentials_exception
    res = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
    session = res.scalars().first()
    now = datetime.now(UTC)
    if not session or session.user_id != user.id:
        raise credentials_exception
    if session.revoked_at is not None:
        raise credentials_exception
    expires_at = session.expires_at
    if expires_at is None:
        raise credentials_exception
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise credentials_exception
    update_last_seen = False
    last_seen_at = session.last_seen_at
    if last_seen_at is None:
        update_last_seen = True
    else:
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        if now - last_seen_at >= timedelta(seconds=30):
            update_last_seen = True
    if update_last_seen:
        session.last_seen_at = now
        await db.commit()
    return user
