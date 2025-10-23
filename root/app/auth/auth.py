import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    verify_and_update_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.observability import get_request_id
from app.localization import resolve_locale, translate
from app.models.models import ActiveSession, FailedLoginAttempt, User
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
        secure=settings.cookie_secure,
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
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _lockout_rules() -> list[tuple[int, int]]:
    raw = settings.auth_lockout_thresholds
    tokens: Sequence[str]
    if isinstance(raw, str):
        tokens = [token.strip() for token in raw.split(",")]
    else:
        tokens = [str(token).strip() for token in raw]

    rules: list[tuple[int, int]] = []
    for token in tokens:
        if not token:
            continue
        threshold_str, _, duration_str = token.partition(":")
        if not threshold_str or not duration_str:
            continue
        try:
            threshold = int(threshold_str)
            duration = int(duration_str)
        except ValueError:
            continue
        if threshold > 0 and duration > 0:
            rules.append((threshold, duration))
    rules.sort(key=lambda item: item[0])
    return rules


def _max_lockout_threshold() -> int:
    rules = _lockout_rules()
    if not rules:
        return 0
    return max(threshold for threshold, _ in rules)


async def _prune_stale_attempts(db: AsyncSession, email: str) -> None:
    history_minutes = getattr(settings, "auth_lockout_history_minutes", 0)
    if history_minutes <= 0:
        return
    cutoff = datetime.now(UTC) - timedelta(minutes=history_minutes)
    await db.execute(
        delete(FailedLoginAttempt)
        .where(FailedLoginAttempt.email == email)
        .where(FailedLoginAttempt.attempted_at < cutoff)
    )
    await db.flush()


async def _fetch_recent_attempts(
    db: AsyncSession, email: str, limit: int, *, for_update: bool = False
) -> list[FailedLoginAttempt]:
    if limit <= 0:
        limit = 1
    stmt = (
        select(FailedLoginAttempt)
        .where(FailedLoginAttempt.email == email)
        .order_by(FailedLoginAttempt.attempted_at.desc())
        .limit(limit)
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    attempts = list(result.scalars().all())
    attempts.reverse()
    return attempts


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _calculate_lock_until(
    attempts: Sequence[FailedLoginAttempt], now: datetime
) -> datetime | None:
    rules = _lockout_rules()
    if not attempts or not rules:
        return None
    total = len(attempts)
    lock_until: datetime | None = None
    for threshold, seconds in rules:
        if total >= threshold:
            attempt_time = _normalize_timestamp(attempts[-1].attempted_at)
            candidate = attempt_time + timedelta(seconds=seconds)
            if candidate > now:
                lock_until = candidate if lock_until is None else max(lock_until, candidate)
    return lock_until


async def _active_lockout(db: AsyncSession, email: str) -> datetime | None:
    if not _lockout_rules():
        return None
    await _prune_stale_attempts(db, email)
    limit = max(_max_lockout_threshold(), 1)
    attempts = await _fetch_recent_attempts(db, email, limit)
    lock_until = _calculate_lock_until(attempts, datetime.now(UTC))
    await db.commit()
    return lock_until


async def _register_failed_attempt(
    db: AsyncSession, email: str, user_id: int | None
) -> tuple[datetime | None, bool, int]:
    limit = max(_max_lockout_threshold(), 1)
    await _prune_stale_attempts(db, email)
    existing = await _fetch_recent_attempts(db, email, limit, for_update=True)
    now = datetime.now(UTC)
    previous_lock = _calculate_lock_until(existing, now)
    attempt = FailedLoginAttempt(email=email, user_id=user_id, attempted_at=now)
    db.add(attempt)
    await db.flush()
    updated = (existing + [attempt])[-limit:]
    lock_until = _calculate_lock_until(updated, now)
    await db.commit()
    triggered = bool(
        lock_until and (previous_lock is None or previous_lock <= now) and lock_until > now
    )
    return lock_until, triggered, len(updated)


async def _clear_failed_attempts(db: AsyncSession, email: str) -> int:
    result = await db.execute(
        delete(FailedLoginAttempt).where(FailedLoginAttempt.email == email)
    )
    await db.commit()
    return int(result.rowcount or 0)


def _pluralize_en(value: int, unit: str) -> str:
    forms = {
        "seconds": "second",
        "minutes": "minute",
        "hours": "hour",
    }
    singular = forms.get(unit, unit)
    if value == 1:
        return singular
    return f"{singular}s"


def _pluralize_ru(value: int, unit: str) -> str:
    forms = {
        "seconds": ("секунду", "секунды", "секунд"),
        "minutes": ("минуту", "минуты", "минут"),
        "hours": ("час", "часа", "часов"),
    }
    singular, few, many = forms.get(unit, (unit, unit, unit))
    value_mod = value % 100
    if 11 <= value_mod <= 14:
        return many
    remainder = value % 10
    if remainder == 1:
        return singular
    if 2 <= remainder <= 4:
        return few
    return many


def _format_duration(locale: str, seconds: int) -> str:
    clamped = max(seconds, 0)
    if clamped < 60:
        value = max(clamped, 1)
        unit = "seconds"
    elif clamped < 3600:
        value = max(1, math.ceil(clamped / 60))
        unit = "minutes"
    else:
        value = max(1, math.ceil(clamped / 3600))
        unit = "hours"

    if locale == "ru":
        unit_text = _pluralize_ru(value, unit)
    else:
        unit_text = _pluralize_en(value, unit)
    return f"{value} {unit_text}"


def _lockout_message(locale: str, lock_until: datetime) -> tuple[str, int]:
    base = translate("errors.auth.account_locked", locale=locale)
    now = datetime.now(UTC)
    remaining_seconds = max(0, int(math.ceil((lock_until - now).total_seconds())))
    if remaining_seconds <= 0:
        return base, 0
    duration_text = _format_duration(locale, remaining_seconds)
    retry_text = translate(
        "errors.auth.account_locked_retry",
        locale=locale,
        duration=duration_text,
    )
    detail = f"{base} {retry_text}".strip()
    retry_after = max(1, remaining_seconds)
    return detail, retry_after


async def _perform_login(
    email: str,
    password: str,
    request: Request,
    response: Response,
    db: AsyncSession,
) -> dict[str, str]:
    normalized_email = email.strip().lower()
    base_locale = resolve_locale(request=request)

    res = await db.execute(select(User).where(User.email == normalized_email))
    user = res.scalars().first()
    locale = resolve_locale(request=request, user=user) if user else base_locale

    lock_until = await _active_lockout(db, normalized_email)
    if lock_until:
        detail, retry_after = _lockout_message(locale, lock_until)
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id if user else None,
            reason="locked",
            extra={"lock_until": lock_until.isoformat()},
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )

    if not user:
        lock_until, triggered, attempts = await _register_failed_attempt(
            db, normalized_email, None
        )
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            reason="invalid_credentials",
        )
        if triggered and lock_until:
            detail, retry_after = _lockout_message(base_locale, lock_until)
            _audit_log(
                "auth.login.locked",
                request,
                level=logging.WARNING,
                reason="lockout",
                extra={
                    "lock_until": lock_until.isoformat(),
                    "attempts": attempts,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
            )
        message = translate("errors.auth.credentials_invalid", locale=base_locale)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    verified, new_hash = verify_and_update_password(password, user.hashed_password)
    if not verified:
        lock_until, triggered, attempts = await _register_failed_attempt(
            db, normalized_email, user.id
        )
        _audit_log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="invalid_credentials",
        )
        if triggered and lock_until:
            detail, retry_after = _lockout_message(locale, lock_until)
            _audit_log(
                "auth.login.locked",
                request,
                level=logging.WARNING,
                user_id=user.id,
                reason="lockout",
                extra={
                    "lock_until": lock_until.isoformat(),
                    "attempts": attempts,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
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

    if new_hash:
        user.hashed_password = new_hash

    cleared = await _clear_failed_attempts(db, normalized_email)
    if cleared:
        _audit_log(
            "auth.login.unlocked",
            request,
            user_id=user.id,
            reason="successful_login",
            extra={"cleared_attempts": cleared},
        )
    if new_hash:
        await db.refresh(user)

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    now = datetime.now(UTC)
    token = await create_access_token(
        str(user.id),
        db=db,
        session_metadata={
            "ip_address": client_ip,
            "user_agent": user_agent,
            "last_seen_at": now,
        },
    )
    _set_access_token_cookie(response, token)
    _audit_log(
        "auth.login.success",
        request,
        user_id=user.id,
        reason="authenticated",
    )
    return {"access_token": token, "token_type": "bearer"}


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
    return await _perform_login(
        form_data.username,
        form_data.password,
        request,
        response,
        db,
    )


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
    return await _perform_login(
        payload.email,
        payload.password,
        request,
        response,
        db,
    )


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
    extra: Mapping[str, Any] | None = None,
) -> None:
    request_id = get_request_id() or request.headers.get("x-request-id")
    client_ip = request.client.host if request.client else None
    payload: dict[str, Any] = {"event": event}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    if request_id:
        payload["request_id"] = request_id
    if client_ip:
        payload["ip"] = client_ip
    if reason:
        payload["reason"] = reason
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
            elif isinstance(value, (str, int, float, bool)):
                payload[key] = value
            else:
                payload[key] = str(value)
    logger.log(level, json.dumps(payload, ensure_ascii=False))
