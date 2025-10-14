from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.core.database import get_db
from app.localization import resolve_locale, translate
from app.models.models import User

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
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise credentials_exception
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exception
    return user
