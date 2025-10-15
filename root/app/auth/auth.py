from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    create_access_token,
    get_password_hash,
    verify_and_update_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.localization import resolve_locale, translate
from app.models.models import User
from app.schemas.schemas import Token, UserCreate
from app.utils.ratelimit import sensitive_route_limit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _token_cookie_expiration() -> tuple[int | None, datetime | None]:
    try:
        minutes = int(settings.access_token_expire_minutes)
    except (TypeError, ValueError):
        return None, None

    max_age = minutes * 60
    expires = datetime.now(UTC) + timedelta(minutes=minutes)
    return max_age, expires


def _set_access_token_cookie(response: Response, token: str) -> None:
    max_age, expires = _token_cookie_expiration()
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=max_age,
        expires=expires,
        path="/",
    )


def _clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(
        "access_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="strict",
    )


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    email = form_data.username.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user:
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    locale = resolve_locale(request=request, user=user)
    verified, new_hash = verify_and_update_password(
        form_data.password, user.hashed_password
    )
    if not verified:
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        message = translate("errors.auth.user_deactivated", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = user.id
    if new_hash:
        user.hashed_password = new_hash
        await db.commit()
        await db.refresh(user)
    token = create_access_token(str(user_id))
    _set_access_token_cookie(response, token)
    return {"access_token": token, "token_type": "bearer"}


@router.post(
    "/login-json",
    response_model=Token,
    dependencies=[Depends(sensitive_route_limit())],
)
async def login_json(
    payload: LoginIn,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    email = payload.email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user:
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    locale = resolve_locale(request=request, user=user)
    verified, new_hash = verify_and_update_password(
        payload.password, user.hashed_password
    )
    if not verified:
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        message = translate("errors.auth.user_deactivated", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = user.id
    if new_hash:
        user.hashed_password = new_hash
        await db.commit()
        await db.refresh(user)
    token = create_access_token(str(user_id))
    _set_access_token_cookie(response, token)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register")
async def register(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    email = user.email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    if res.scalars().first():
        locale = resolve_locale(request=request)
        message = translate("errors.users.email_in_use", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    try:
        hashed_password = get_password_hash(user.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    new_user = User(
        email=email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role="student",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"status": "ok", "id": new_user.id}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    """Terminate the client session."""

    _clear_access_token_cookie(response)
    return {"status": "ok"}
