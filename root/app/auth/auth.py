import json
import logging
import math
import secrets
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import (
    get_current_user,
    require_fresh_mfa,
    require_fresh_mfa_for_enrollment,
)
from app.api.users import _attach_pending_email
from app.auth import mfa
from app.auth.security import (
    create_access_token,
    decode_token,
    verify_and_update_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.observability import get_request_id
from app.localization import resolve_locale, translate
from app.models.models import (
    ActiveSession,
    FailedLoginAttempt,
    MfaTotpEnrollment,
    User,
)
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.schemas.schemas import (
    MfaFactorStatusOut,
    MfaTotpEnrollmentOut,
    SessionSigningKeyOut,
    TokenWithProfile,
    UserCreate,
    UserOut,
)
from app.utils.ratelimit import sensitive_route_limit

logger = logging.getLogger("app.auth")


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class MfaMethodChallengeOut(BaseModel):
    method: Literal[mfa.MFA_METHOD_TOTP]
    challenge_token: str
    challenge_expires_at: datetime
    options: dict[str, Any] | None = None
    attempt_count: int | None = None
    attempt_limit: int | None = None
    remaining_attempts: int | None = None


class PendingMfaResponse(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    user_id: int
    session_id: int | None = None
    default_method: Literal[mfa.MFA_METHOD_TOTP] | None = None
    methods: list[MfaMethodChallengeOut]


class TotpEnrollmentStartIn(BaseModel):
    label: str | None = None
    reuse_existing: bool | None = False


class TotpEnrollmentStartOut(BaseModel):
    enrollment: MfaTotpEnrollmentOut
    secret: str
    otpauth_url: str


class TotpEnrollmentConfirmIn(BaseModel):
    enrollment_id: int
    code: str


class MfaVerifyIn(BaseModel):
    method: Literal[mfa.MFA_METHOD_TOTP]
    challenge_token: str
    code: str | None = None


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


def _access_token_lifetime_minutes() -> int:
    try:
        minutes = int(settings.access_token_expire_minutes)
    except (TypeError, ValueError):
        return 60
    return minutes if minutes > 0 else 60


def _extract_client_info(request: Request) -> tuple[str | None, str | None]:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip() or None
    else:
        client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return client_ip, user_agent


def _create_session_for_user(user: User, request: Request) -> ActiveSession:
    client_ip, user_agent = _extract_client_info(request)
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=str(uuid4()),
        expires_at=now,
        last_seen_at=now,
        signing_key=secrets.token_urlsafe(32),
        mfa_required=False,
    )
    if client_ip:
        session.ip_address = client_ip[:64]
    if user_agent:
        session.user_agent = user_agent[:512]
    return session


async def _mint_access_token(
    db: AsyncSession,
    session: ActiveSession,
    *,
    extra: Mapping[str, Any] | None = None,
) -> str:
    minutes = _access_token_lifetime_minutes()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=minutes)
    session.expires_at = expires_at
    session.last_seen_at = now
    payload = {
        "sub": str(session.user_id),
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "jti": session.jti,
    }
    if extra:
        for key, value in extra.items():
            payload[key] = value
    kid = settings.jwt_signing_active_kid
    secret = settings.jwt_signing_active_secret
    token = jwt.encode(
        payload,
        secret,
        algorithm=settings.algorithm,
        headers={"kid": kid},
    )
    await db.commit()
    return token


async def _build_token_response(
    db: AsyncSession,
    user: User,
    token: str,
    session: ActiveSession | None,
) -> TokenWithProfile:
    refreshed_user = await ensure_mfa_relationships_loaded(db, user)
    if refreshed_user is not None:
        user = refreshed_user
    enriched_user = await _attach_pending_email(db, user)
    if enriched_user is not None:
        user = enriched_user
    session_payload: SessionSigningKeyOut | None = None
    signing_key = getattr(session, "signing_key", None) if session else None
    if isinstance(signing_key, str) and signing_key:
        session_payload = SessionSigningKeyOut(signing_key=signing_key)
    return TokenWithProfile(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
        session=session_payload,
    )


async def _resolve_mfa_capabilities(db: AsyncSession, *, user: User) -> dict[str, bool]:
    totp_stmt = (
        select(MfaTotpEnrollment.id)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.is_active.is_(True))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
        .limit(1)
    )
    totp_available = bool((await db.execute(totp_stmt)).scalars().first())
    if not totp_available and user.mfa_default_method == mfa.MFA_METHOD_TOTP:
        legacy_stmt = (
            select(MfaTotpEnrollment.id)
            .where(MfaTotpEnrollment.user_id == user.id)
            .where(MfaTotpEnrollment.is_active.is_(True))
            .where(MfaTotpEnrollment.revoked_at.is_(None))
            .where(MfaTotpEnrollment.confirmed_at.is_(None))
            .limit(1)
        )
        totp_available = bool((await db.execute(legacy_stmt)).scalars().first())
    return {mfa.MFA_METHOD_TOTP: totp_available}


async def _collect_mfa_challenges(
    db: AsyncSession,
    *,
    user: User,
    locale: str,
    capabilities: Mapping[str, bool],
    session: ActiveSession | None = None,
) -> list[MfaMethodChallengeOut]:
    methods: list[MfaMethodChallengeOut] = []
    if not capabilities.get(mfa.MFA_METHOD_TOTP):
        return methods
    challenge = await mfa.start_totp_verification(
        db,
        user=user,
        session=session,
        locale=locale,
    )
    (
        attempt_count,
        attempt_limit,
        remaining_attempts,
    ) = mfa.describe_challenge_attempts(
        challenge, default_limit=settings.mfa_totp_attempt_limit
    )
    methods.append(
        MfaMethodChallengeOut(
            method=mfa.MFA_METHOD_TOTP,
            challenge_token=challenge.token,
            challenge_expires_at=challenge.expires_at,
            attempt_count=attempt_count,
            attempt_limit=attempt_limit,
            remaining_attempts=remaining_attempts,
        )
    )
    return methods


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
                lock_until = (
                    candidate if lock_until is None else max(lock_until, candidate)
                )
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
        lock_until
        and (previous_lock is None or previous_lock <= now)
        and lock_until > now
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
) -> dict[str, str] | JSONResponse:
    normalized_email = email.strip().lower()
    base_locale = resolve_locale(request=request)

    res = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
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

    refreshed_user = await ensure_mfa_relationships_loaded(db, user)
    if refreshed_user is not None:
        user = refreshed_user
    capabilities = await _resolve_mfa_capabilities(db, user=user)
    available_methods = [method for method, enabled in capabilities.items() if enabled]
    require_mfa = bool(available_methods) or bool(user.mfa_required)
    if user.mfa_required and not available_methods:
        _audit_log(
            "auth.login.mfa_missing",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="no_methods",
        )
        message = translate("errors.auth.mfa_totp_missing", locale=locale)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=message)
    if require_mfa and not capabilities.get(mfa.MFA_METHOD_TOTP):
        message = translate("errors.auth.mfa_totp_missing", locale=locale)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=message)
    if require_mfa:
        methods = await _collect_mfa_challenges(
            db,
            user=user,
            locale=locale,
            capabilities=capabilities,
        )
        if methods:
            await db.commit()
            payload = PendingMfaResponse(
                user_id=user.id,
                default_method=user.mfa_default_method or mfa.MFA_METHOD_TOTP,
                methods=methods,
            )
            _audit_log(
                "auth.login.mfa_required",
                request,
                user_id=user.id,
                reason="challenge_issued",
                extra={"methods": [entry.method for entry in methods]},
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=payload.model_dump(mode="json"),
            )

    client_ip, user_agent = _extract_client_info(request)
    now = datetime.now(UTC)
    token_result = await create_access_token(
        str(user.id),
        db=db,
        session_metadata={
            "ip_address": client_ip,
            "user_agent": user_agent,
            "last_seen_at": now,
            "mfa_required": bool(user.mfa_required),
            "mfa_method": user.mfa_default_method,
            "mfa_completed_at": now,
            "mfa_verified_at": now,
        },
    )
    if isinstance(token_result, tuple):
        token, session = token_result
    else:
        token = cast(str, token_result)
        session = None
    _set_access_token_cookie(response, token)
    _audit_log(
        "auth.login.success",
        request,
        user_id=user.id,
        reason="authenticated",
    )
    return await _build_token_response(db, user, token, session)


@router.post(
    "/login",
    response_model=TokenWithProfile,
    responses={status.HTTP_202_ACCEPTED: {"model": PendingMfaResponse}},
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
    response_model=TokenWithProfile,
    responses={status.HTTP_202_ACCEPTED: {"model": PendingMfaResponse}},
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


@router.post(
    "/mfa/totp/start",
    response_model=TotpEnrollmentStartOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def start_totp_enrollment_endpoint(
    request: Request,
    payload: TotpEnrollmentStartIn | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    label = payload.label if payload else None
    reuse_existing = bool(payload.reuse_existing) if payload else False
    enrollment, secret, otpauth_url = await mfa.start_totp_enrollment(
        db,
        user=user,
        label=label,
        reuse_existing=reuse_existing,
    )
    await db.commit()
    await db.refresh(enrollment)
    _audit_log(
        "auth.mfa.totp.enroll_start",
        request,
        user_id=user.id,
        reason="issued",
        extra={"enrollment_id": enrollment.id, "label": label},
    )
    return TotpEnrollmentStartOut(
        enrollment=MfaTotpEnrollmentOut.model_validate(enrollment),
        secret=secret,
        otpauth_url=otpauth_url,
    )


@router.post(
    "/mfa/totp/confirm",
    response_model=MfaTotpEnrollmentOut,
    dependencies=[Depends(require_fresh_mfa_for_enrollment)],
)
async def confirm_totp_enrollment(
    payload: TotpEnrollmentConfirmIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    enrollment = await db.get(MfaTotpEnrollment, payload.enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    try:
        updated = await mfa.complete_totp_enrollment(
            db, enrollment=enrollment, code=payload.code
        )
    except HTTPException:
        _audit_log(
            "auth.mfa.totp.enroll_failure",
            request,
            user_id=user.id,
            reason="invalid_code",
            extra={"enrollment_id": payload.enrollment_id},
        )
        raise
    await mfa.refresh_user_mfa_preferences(db, user=user)
    await db.commit()
    await db.refresh(updated)
    _audit_log(
        "auth.mfa.totp.enroll_complete",
        request,
        user_id=user.id,
        reason="confirmed",
        extra={"enrollment_id": updated.id},
    )
    return MfaTotpEnrollmentOut.model_validate(updated)


@router.get("/mfa/totp", response_model=list[MfaTotpEnrollmentOut])
async def list_totp_enrollments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
        .order_by(MfaTotpEnrollment.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        MfaTotpEnrollmentOut.model_validate(enrollment)
        for enrollment in result.scalars()
    ]


@router.delete(
    "/mfa/totp/pending/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_pending_totp_enrollment(
    enrollment_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    enrollment = await db.get(MfaTotpEnrollment, enrollment_id)
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    if enrollment.confirmed_at is not None or enrollment.revoked_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enrollment is not pending")

    await db.delete(enrollment)
    await db.commit()
    _audit_log(
        "auth.mfa.totp.pending_cancel",
        request,
        user_id=user.id,
        reason="pending_cancelled",
        extra={"enrollment_id": enrollment_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/mfa/totp/{enrollment_id}", response_model=MfaFactorStatusOut)
async def delete_totp_enrollment(
    enrollment_id: int,
    request: Request,
    _: None = Depends(require_fresh_mfa),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    disabled_count = await mfa.disable_totp(db, user=user, enrollment_id=enrollment_id)
    await mfa.refresh_user_mfa_preferences(db, user=user)
    payload = MfaFactorStatusOut(
        disabled=bool(disabled_count),
        mfa_default_method=user.mfa_default_method,
        mfa_required=bool(user.mfa_required),
    )
    await db.commit()
    _audit_log(
        "auth.mfa.totp.disabled",
        request,
        user_id=user.id,
        reason="revoked",
        extra={
            "disabled": bool(disabled_count),
            "enrollment_id": enrollment_id,
            "default_method": payload.mfa_default_method,
            "mfa_required": payload.mfa_required,
        },
    )
    return payload


@router.post("/mfa/verify", response_model=TokenWithProfile)
async def verify_mfa_challenge(
    payload: MfaVerifyIn,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    expected_type = mfa.CHALLENGE_TYPE_TOTP_VERIFY
    try:
        challenge = await mfa.get_challenge(
            db,
            token=payload.challenge_token,
            challenge_type=expected_type,
            consume=False,
        )
    except HTTPException as exc:
        _audit_log(
            "auth.mfa.verify.failure",
            request,
            reason="challenge_lookup",
            extra={"method": payload.method, "status_code": exc.status_code},
        )
        raise
    user = await db.get(User, challenge.user_id)
    if not user or not user.is_active:
        _audit_log(
            "auth.mfa.verify.failure",
            request,
            user_id=challenge.user_id,
            reason="user_unavailable",
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challenge user unavailable")
    locale = resolve_locale(request=request, user=user)
    session: ActiveSession | None = None
    now = datetime.now(UTC)
    if challenge.session_id is not None:
        session = await db.get(ActiveSession, challenge.session_id)
        if not session or session.user_id != user.id:
            _audit_log(
                "auth.mfa.verify.failure",
                request,
                user_id=user.id,
                reason="session_invalid",
                extra={"session_id": challenge.session_id},
            )
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Associated session is invalid"
            )
        if session.revoked_at is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Associated session has been revoked"
            )
        expires_at = session.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Associated session has expired"
                )
    _audit_log(
        "auth.mfa.verify.attempt",
        request,
        user_id=user.id,
        reason=payload.method,
        extra={
            "challenge_type": challenge.challenge_type,
            "session_id": challenge.session_id,
        },
    )
    try:
        if not payload.code:
            _audit_log(
                "auth.mfa.verify.failure",
                request,
                user_id=user.id,
                reason="missing_code",
            )
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Verification code required"
            )
        await mfa.verify_totp_for_user(
            db,
            user=user,
            code=payload.code,
            challenge=challenge,
            session_id=challenge.session_id,
            locale=locale,
        )
    except HTTPException as exc:
        await db.commit()
        _audit_log(
            "auth.mfa.verify.failure",
            request,
            user_id=user.id,
            reason=payload.method,
            extra={"status_code": exc.status_code},
        )
        raise
    if session is None:
        session = _create_session_for_user(user, request)
        db.add(session)
        await db.flush()
    request.state.active_session = session
    await mfa.record_mfa_success(db, user=user, session=session, method=payload.method)
    token = await _mint_access_token(db, session)
    _set_access_token_cookie(response, token)
    await db.commit()
    _audit_log(
        "auth.mfa.verify.success",
        request,
        user_id=user.id,
        reason=payload.method,
        extra={
            "session_id": session.id,
            "challenge_type": challenge.challenge_type,
        },
    )
    if challenge.session_id is None:
        _audit_log(
            "auth.login.success",
            request,
            user_id=user.id,
            reason="authenticated",
        )
    else:
        _audit_log(
            "auth.mfa.step_up.completed",
            request,
            user_id=user.id,
            reason="verified",
            extra={"session_id": session.id},
        )
    return await _build_token_response(db, user, token, session)


@router.post(
    "/mfa/step-up",
    response_model=PendingMfaResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": PendingMfaResponse}},
)
async def request_step_up(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = getattr(request.state, "active_session", None)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Active session required")
    locale = resolve_locale(request=request, user=user)
    capabilities = await _resolve_mfa_capabilities(db, user=user)
    methods = await _collect_mfa_challenges(
        db,
        user=user,
        locale=locale,
        capabilities=capabilities,
        session=session,
    )
    if not methods:
        message = translate("errors.auth.mfa_totp_missing", locale=locale)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=message)
    await db.commit()
    payload = PendingMfaResponse(
        user_id=user.id,
        session_id=session.id,
        default_method=user.mfa_default_method or mfa.MFA_METHOD_TOTP,
        methods=methods,
    )
    _audit_log(
        "auth.mfa.step_up.requested",
        request,
        user_id=user.id,
        reason="challenge_issued",
        extra={"session_id": session.id, "methods": [m.method for m in methods]},
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=payload.model_dump(mode="json"),
    )


@router.get("/session/signing-key", response_model=SessionSigningKeyOut)
async def get_session_signing_key(
    request: Request, _: User = Depends(get_current_user)
):
    session = getattr(request.state, "active_session", None)
    if session is None or not getattr(session, "signing_key", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate(
                "errors.sessions.signing_key_missing",
                locale=resolve_locale(request=request),
            ),
        )
    return SessionSigningKeyOut(signing_key=session.signing_key)


@router.post("/register", dependencies=[Depends(sensitive_route_limit())])
async def register(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    try:
        new_user = await crud.create_user(db, user)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        await db.rollback()
        message = translate("errors.users.create_failed", locale=locale)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc

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
        if session:
            now = datetime.now(UTC)
            revoked_at = session.revoked_at or now
            session.revoked_at = revoked_at
            session.signing_key = secrets.token_urlsafe(32)
            await db.commit()
            await db.refresh(session)
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
            elif isinstance(value, str | int | float | bool):
                payload[key] = value
            else:
                payload[key] = str(value)
    logger.log(level, json.dumps(payload, ensure_ascii=False))
