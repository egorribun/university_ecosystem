import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    verify_and_update_password,
)
from app.core.config import settings
from app.core.observability import get_request_id
from app.core.database import get_db
from app.localization import resolve_locale, translate
from app.models.models import ActiveSession, User
from app.schemas.schemas import Token, UserCreate
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger("app.auth")


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
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            reason="invalid_credentials",
        )
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
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="invalid_credentials",
        )
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="inactive_user",
        )
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
    token = await create_access_token(str(user_id), db=db)
    _set_access_token_cookie(response, token)
    _audit_log(
        "auth.login.success",
        request,
        user_id=user_id,
        reason="authenticated",
    )
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
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            reason="invalid_credentials",
        )
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
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="invalid_credentials",
        )
        message = translate("errors.auth.credentials_invalid", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="inactive_user",
        )
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
    token = await create_access_token(str(user_id), db=db)
    _set_access_token_cookie(response, token)
    _audit_log(
        "auth.login.success",
        request,
        user_id=user_id,
        reason="authenticated",
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register", dependencies=[Depends(sensitive_route_limit())])
async def register(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    email = user.email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    if res.scalars().first():
        message = translate("errors.users.email_in_use", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    try:
        hashed_password = get_password_hash(user.password, locale=locale)
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
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Terminate the client session."""

    raw_token: str | None = None
    auth_header = request.headers.get("Authorization")
    if auth_header:
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer":
            raw_token = value.strip() or None
    if raw_token is None:
        raw_token = request.cookies.get("access_token")

    payload = decode_token(raw_token) if raw_token else None
    jti = payload.get("jti") if payload else None
    if jti:
        res = await db.execute(select(ActiveSession).where(ActiveSession.jti == jti))
        session = res.scalars().first()
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            await db.commit()
            _audit_log(
                "auth.logout.revoked",
                request,
                user_id=session.user_id,
                reason="user_initiated",
            )

    _clear_access_token_cookie(response)
    return {"status": "ok"}


def _audit_log(
    event: str,
    request: Request,
    *,
    level: int = logging.INFO,
    user_id: int | str | None = None,
    reason: str | None = None,
) -> None:
    request_id = get_request_id() or request.headers.get("x-request-id")
    client_ip = request.client.host if request.client else None
    payload: dict[str, str] = {"event": event}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    if request_id:
        payload["request_id"] = request_id
    if client_ip:
        payload["ip"] = client_ip
    if reason:
        payload["reason"] = reason
    logger.log(level, json.dumps(payload, ensure_ascii=False))

