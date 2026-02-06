"""Helpers for managing multi-factor authentication secrets and challenges."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pyotp
from fastapi import status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import raise_http_error, raise_validation_error
from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_VERIFY,
    CHALLENGE_TYPE_WEBAUTHN_AUTH,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.auth.security import get_password_hash, verify_password
from app.core.config import settings
from app.core.localization import translate
from app.core.rate_limit import RateLimitExceeded, enforce_rate_limit
from app.models.models import (
    ActiveSession,
    MfaChallenge,
    MfaTotpEnrollment,
    RecoveryCode,
    TrustedDevice,
    User,
    WebAuthnCredential,
)
from app.services.session_cleanup import revoke_sessions_matching
from app.utils import ratelimit as ratelimit_utils

_TOTP_SECRET_LENGTH = 32
_TOTP_VALID_WINDOW = settings.mfa_totp_initial_skew_windows
_TOTP_DIGITS = 6
_MAX_ACTIVE_TOTP_ENROLLMENTS = 1

TOTP_ENROLLMENT_PENDING_ERROR = (
    "A TOTP enrollment is already pending. "
    "Confirm or reuse it before starting a new one."
)
TOTP_ENROLLMENT_LIMIT_ERROR = (
    "Only one authenticator app can be connected at a time. "
    "Remove the existing app before starting a new setup."
)

CHALLENGE_TYPE_TOTP_AUTH = CHALLENGE_TYPE_TOTP_VERIFY


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.users.audit")


@dataclass(slots=True)
class MfaResetStats:
    totp_deleted: int = 0
    webauthn_deleted: int = 0
    recovery_codes_deleted: int = 0
    challenges_revoked: int = 0
    fields_cleared: bool = False

    @property
    def changed(self) -> bool:
        return any(
            (
                self.totp_deleted,
                self.webauthn_deleted,
                self.challenges_revoked,
                self.fields_cleared,
            )
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def user_has_confirmed_interactive_factor(user: User) -> bool:
    """Return True if the user has at least one confirmed interactive factor."""

    if user.mfa_default_method:
        return True

    # Check WebAuthn
    if getattr(user, "webauthn_credentials", None):
        return True

    enrollments = getattr(user, "totp_enrollments", None)
    if not enrollments:
        return False
    for enrollment in enrollments:
        if enrollment.revoked_at is None and enrollment.confirmed_at is not None:
            return True
    return False


async def has_totp_enabled(db: AsyncSession, user: User) -> bool:
    """Return True if the user has at least one active TOTP enrollment."""
    # Use relationship if loaded, or query DB
    enrollments = getattr(user, "totp_enrollments", None)
    if enrollments is not None:
        for e in enrollments:
            if e.confirmed_at is not None and e.revoked_at is None:
                return True
        return False

    # Fallback to DB query
    stmt = select(func.count(MfaTotpEnrollment.id)).where(
        MfaTotpEnrollment.user_id == user.id,
        MfaTotpEnrollment.confirmed_at.is_not(None),
        MfaTotpEnrollment.revoked_at.is_(None),
    )
    res = await db.execute(stmt)
    return bool(res.scalar())


async def has_webauthn_enabled(db: AsyncSession, user: User) -> bool:
    """Return True if the user has at least one WebAuthn credential."""
    credentials = getattr(user, "webauthn_credentials", None)
    if credentials is not None:
        return len(credentials) > 0

    stmt = select(func.count(WebAuthnCredential.id)).where(
        WebAuthnCredential.user_id == user.id
    )
    res = await db.execute(stmt)
    return bool(res.scalar())


async def user_has_active_factor(db: AsyncSession, user: User) -> bool:
    """Return True if the user has any active MFA factor.

    This includes unconfirmed legacy ones.
    """
    # Check loaded TOTP enrollments
    enrollments = getattr(user, "totp_enrollments", None)
    if enrollments is not None:
        for e in enrollments:
            if e.is_active and e.revoked_at is None:
                return True
    else:
        # DB check
        stmt = select(func.count(MfaTotpEnrollment.id)).where(
            MfaTotpEnrollment.user_id == user.id,
            MfaTotpEnrollment.is_active.is_(True),
            MfaTotpEnrollment.revoked_at.is_(None),
        )
        res = await db.execute(stmt)
        if res.scalar() > 0:
            return True

    # Check WebAuthn
    credentials = getattr(user, "webauthn_credentials", None)
    if credentials is not None:
        if len(credentials) > 0:
            return True
    else:
        stmt = select(func.count(WebAuthnCredential.id)).where(
            WebAuthnCredential.user_id == user.id
        )
        res = await db.execute(stmt)
        if res.scalar() > 0:
            return True

    return False


def _base64url_encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("utf-8")
    return encoded.rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_totp_secret(length: int = _TOTP_SECRET_LENGTH) -> str:
    return pyotp.random_base32(length=length)


def build_totp_uri(secret: str, *, account_name: str, issuer: str | None = None) -> str:
    issuer_name = issuer or settings.mfa_totp_issuer
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    return totp.provisioning_uri(name=account_name, issuer_name=issuer_name)


def verify_totp(secret: str, code: str, *, window: int | None = None) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != _TOTP_DIGITS:
        logger.warning(
            "TOTP verify failed: length mismatch (expected %s digits)",
            _TOTP_DIGITS,
        )
        return False
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    valid_window = _TOTP_VALID_WINDOW if window is None else window

    result = totp.verify(
        normalized,
        valid_window=valid_window,
        for_time=None,
    )
    if not result:
        logger.warning(
            "TOTP verify failed (server time: %s)",
            _utcnow(),
        )
    return bool(result)


def _resolve_rate_limit_backend() -> str | None:
    backend = settings.rate_limit_storage_backend.strip().lower()
    uri = settings.rate_limit_storage_uri.strip()
    if backend == "redis" and uri.lower().startswith(("redis://", "rediss://")):
        return uri
    return None


async def _enforce_challenge_rate_limit(
    *,
    user_id: UUID,
    challenge_type: str,
    locale: str | None = None,
) -> None:
    limit = max(0, settings.mfa_challenge_max_attempts)
    window = max(0, settings.mfa_challenge_ttl_seconds)
    if limit == 0 or window == 0:
        return
    key = f"mfa:{challenge_type}:{user_id}"
    message = translate("errors.rate_limit.generic", locale=locale)
    redis_url = _resolve_rate_limit_backend()
    if redis_url:
        try:
            await enforce_rate_limit(
                identifier=key,
                namespace="mfa",
                limit=limit,
                window_seconds=window,
                redis_url=redis_url,
            )
        except RateLimitExceeded:
            raise_http_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "errors.rate_limit.generic",
                locale,
            )
    else:
        ratelimit_utils.limiter.check(key, limit, window, message=message)


async def issue_challenge(
    db: AsyncSession,
    *,
    user_id: UUID,
    challenge_type: str,
    session_id: UUID | None = None,
    payload: MutableMapping[str, Any] | None = None,
    ttl_seconds: int | None = None,
    locale: str | None = None,
    attempt_limit: int | None = None,
) -> MfaChallenge:
    await _enforce_challenge_rate_limit(
        user_id=user_id, challenge_type=challenge_type, locale=locale
    )
    token = secrets.token_urlsafe(48)
    now = _utcnow()
    ttl = (
        ttl_seconds
        if ttl_seconds and ttl_seconds > 0
        else settings.mfa_challenge_ttl_seconds
    )
    expires_at = now + timedelta(seconds=ttl)
    payload_data = dict(payload or {})
    if attempt_limit is not None and attempt_limit > 0:
        payload_data.setdefault("attempt_limit", attempt_limit)
    challenge = MfaChallenge(
        user_id=user_id,
        session_id=session_id,
        challenge_type=challenge_type,
        token=token,
        expires_at=expires_at,
        payload=payload_data,
    )
    db.add(challenge)
    await db.flush()
    return challenge


def _extract_attempt_limit(
    challenge: MfaChallenge | None, fallback: int | None = None
) -> int | None:
    limit = fallback
    if challenge and isinstance(challenge.payload, Mapping):
        raw_limit = challenge.payload.get("attempt_limit")
        if isinstance(raw_limit, int):
            limit = raw_limit
    if limit is None:
        return None
    try:
        resolved = int(limit)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
    if resolved <= 0:
        return None
    return resolved


def describe_challenge_attempts(
    challenge: MfaChallenge,
    *,
    default_limit: int | None = None,
) -> tuple[int, int | None, int | None]:
    attempts = int(getattr(challenge, "attempt_count", 0) or 0)
    limit = _extract_attempt_limit(challenge, default_limit)
    remaining: int | None = None
    if limit is not None:
        remaining = max(limit - attempts, 0)
    return attempts, limit, remaining


async def _lock_challenge(
    db: AsyncSession,
    challenge: MfaChallenge,
    *,
    method: str,
    limit: int | None,
    locale: str | None,
    status_code: int = status.HTTP_429_TOO_MANY_REQUESTS,
) -> None:
    challenge.consumed_at = _utcnow()
    await db.commit()
    audit_logger.warning(
        json.dumps(
            {
                "event": "auth.mfa.challenge.locked",
                "user_id": challenge.user_id,
                # Redacted metadata for CodeQL check
                "challenge_id": challenge.id,
            },
            default=str,
        )
    )  # Log only non-sensitive metadata. No secrets are logged.

    raise_http_error(
        status_code,
        "errors.auth.mfa_challenge_locked",
        locale,
    )


async def _ensure_challenge_not_locked(
    db: AsyncSession,
    challenge: MfaChallenge | None,
    *,
    method: str,
    limit: int | None,
    locale: str | None,
    status_code: int = status.HTTP_429_TOO_MANY_REQUESTS,
) -> None:
    if challenge is None or limit is None:
        return
    attempts = int(getattr(challenge, "attempt_count", 0) or 0)
    if attempts >= limit:
        await _lock_challenge(
            db,
            challenge,
            method=method,
            limit=limit,
            locale=locale,
            status_code=status_code,
        )


async def _register_failed_attempt(
    db: AsyncSession,
    challenge: MfaChallenge | None,
    *,
    method: str,
    limit: int | None,
    locale: str | None,
    status_code: int = status.HTTP_429_TOO_MANY_REQUESTS,
) -> None:
    if challenge is None:
        return
    current = int(getattr(challenge, "attempt_count", 0) or 0)
    challenge.attempt_count = current + 1
    await db.commit()  # Ensure persistence even on exception
    # Re-acquire challenge after commit (to bind to new transaction)
    stmt = select(MfaChallenge).where(MfaChallenge.id == challenge.id)
    challenge = (await db.execute(stmt)).scalars().first()
    if challenge is None:
        return  # Should not happen
    if limit is not None and challenge.attempt_count >= limit:
        await _lock_challenge(
            db,
            challenge,
            method=method,
            limit=limit,
            locale=locale,
            status_code=status_code,
        )


async def get_challenge(
    db: AsyncSession,
    *,
    token: str,
    challenge_type: str | list[str],
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    consume: bool = False,
    locale: str = "en",
) -> MfaChallenge:
    stmt = select(MfaChallenge).where(MfaChallenge.token == token).with_for_update()
    if isinstance(challenge_type, list):
        stmt = stmt.where(MfaChallenge.challenge_type.in_(challenge_type))
    else:
        stmt = stmt.where(MfaChallenge.challenge_type == challenge_type)
    if user_id is not None:
        stmt = stmt.where(MfaChallenge.user_id == user_id)
    if session_id is not None:
        stmt = stmt.where(MfaChallenge.session_id == session_id)
    result = await db.execute(stmt)
    challenge = result.scalars().first()
    if not challenge:
        raise_http_error(
            status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
        )
    now = _utcnow()
    expires_at = challenge.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    consumed_at = challenge.consumed_at
    if consumed_at is not None and consumed_at.tzinfo is None:
        consumed_at = consumed_at.replace(tzinfo=UTC)
    if consumed_at is not None or (expires_at is not None and expires_at <= now):
        raise_http_error(
            status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
        )
    if consume:
        challenge.consumed_at = now
        await db.flush()
    return challenge


async def consume_challenge(
    db: AsyncSession,
    *,
    challenge_token: str,
    challenge_type: str | list[str],
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    provided_code: str | None = None,
    provided_webauthn_response: dict[str, Any] | None = None,
    provided_recovery_code: str | None = None,
    provided_method: str | None = None,
    locale: str = "en",
) -> tuple[MfaChallenge, ActiveSession | None]:
    challenge = await get_challenge(
        db,
        token=challenge_token,
        challenge_type=challenge_type,
        user_id=user_id,
        session_id=session_id,
        consume=False,  # Don't consume yet
        locale=locale,
    )

    # Initial lock and attempt check
    limit = _extract_attempt_limit(challenge, settings.mfa_challenge_max_attempts)
    await _ensure_challenge_not_locked(
        db,
        challenge,
        method=provided_method or "unknown",
        limit=limit,
        locale=locale,
    )

    mfa_session = None
    if challenge.session_id:
        mfa_session = await db.get(ActiveSession, challenge.session_id)
        if mfa_session and mfa_session.revoked_at:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST,
                "Associated session has been revoked",
                locale,
            )

    # Verification logic based on method or type
    v_method = provided_method
    if v_method is None:
        if challenge.challenge_type in [
            CHALLENGE_TYPE_TOTP_VERIFY,
            CHALLENGE_TYPE_TOTP_AUTH,
        ]:
            v_method = MFA_METHOD_TOTP
        elif challenge.challenge_type == CHALLENGE_TYPE_WEBAUTHN_AUTH:
            v_method = MFA_METHOD_WEBAUTHN
        elif challenge.challenge_type == CHALLENGE_TYPE_RECOVERY_CODE:
            v_method = MFA_METHOD_RECOVERY_CODE

    if v_method == MFA_METHOD_TOTP:
        if not provided_code:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )

        user = await db.get(User, challenge.user_id)
        # Verify TOTP code
        enrollments_stmt = select(MfaTotpEnrollment).where(
            MfaTotpEnrollment.user_id == user.id,
            MfaTotpEnrollment.is_active.is_(True),
            MfaTotpEnrollment.revoked_at.is_(None),
        )
        result = await db.execute(enrollments_stmt)
        enrollments = result.scalars().all()

        valid = False
        for enrollment in enrollments:
            if not enrollment.secret:
                continue
            totp = pyotp.TOTP(enrollment.secret)
            if totp.verify(provided_code, valid_window=1):
                valid = True
                break

        if not valid:
            await _register_failed_attempt(
                db,
                challenge,
                method=MFA_METHOD_TOTP,
                limit=settings.mfa_totp_attempt_limit,
                locale=locale,
            )
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_code", locale
            )

    elif v_method == MFA_METHOD_RECOVERY_CODE:
        # For recovery code, we use provided_code
        if not provided_code:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )
        user = await db.get(User, challenge.user_id)
        if not await verify_recovery_code(db, user=user, code=provided_code):
            await _register_failed_attempt(
                db,
                challenge,
                method=MFA_METHOD_RECOVERY_CODE,
                limit=settings.mfa_challenge_max_attempts,
                locale=locale,
            )
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_code", locale
            )

    elif v_method == MFA_METHOD_WEBAUTHN:
        from app.services.webauthn import WebAuthnService

        if not provided_webauthn_response:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )

        service = WebAuthnService(db)
        user = await db.get(User, challenge.user_id)
        try:
            await service.verify_authentication(
                user,
                challenge.payload["options"]["challenge"],
                provided_webauthn_response,
            )
        except Exception:
            await _register_failed_attempt(
                db,
                challenge,
                method=MFA_METHOD_WEBAUTHN,
                limit=settings.mfa_challenge_max_attempts,
                locale=locale,
            )
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_code", locale
            )

    # If we reached here, verification was successful.
    challenge.consumed_at = _utcnow()
    await db.commit()

    return challenge, mfa_session


async def purge_expired_challenges(
    db: AsyncSession,
    *,
    grace_period_seconds: int | None = None,
    now: datetime | None = None,
) -> int:
    if now is None:
        now = _utcnow()
    grace_seconds = max(0, int(grace_period_seconds or 0))
    cutoff = now - timedelta(seconds=grace_seconds)
    delete_stmt = (
        delete(MfaChallenge)
        .where(MfaChallenge.expires_at <= cutoff)
        .where(
            or_(
                MfaChallenge.consumed_at.is_(None),
                MfaChallenge.consumed_at <= cutoff,
            )
        )
    )
    result = await db.execute(delete_stmt)
    await db.flush()
    return int(result.rowcount or 0)


async def start_totp_enrollment(
    db: AsyncSession,
    *,
    user: User,
    label: str | None = None,
    reuse_existing: bool = False,
) -> tuple[MfaTotpEnrollment, str, str]:
    pending_stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.confirmed_at.is_(None))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .order_by(MfaTotpEnrollment.created_at.desc())
        .with_for_update()
    )
    result = await db.execute(pending_stmt)
    pending = result.scalars().first()
    if pending:
        if not reuse_existing:
            raise_validation_error("errors.mfa.totp_enrollment_pending", "en")
        if label and label != pending.label:
            pending.label = label
            await db.flush()
        account_name = label or pending.label or user.email
        otpauth_url = build_totp_uri(pending.secret, account_name=account_name)
        return pending, pending.secret, otpauth_url

    count_stmt = (
        select(func.count())
        .select_from(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
    )
    active_count = await db.scalar(count_stmt)
    if active_count and active_count >= _MAX_ACTIVE_TOTP_ENROLLMENTS:
        raise_http_error(
            status.HTTP_400_BAD_REQUEST,
            "errors.mfa.totp_limit_reached",
            "en",
        )

    secret = create_totp_secret()
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=secret,
        label=label or user.email,
        is_active=False,
    )
    db.add(enrollment)
    await db.flush()
    account_name = label or user.email
    otpauth_url = build_totp_uri(secret, account_name=account_name)
    return enrollment, secret, otpauth_url


async def complete_totp_enrollment(
    db: AsyncSession,
    *,
    enrollment: MfaTotpEnrollment,
    code: str,
) -> MfaTotpEnrollment:
    if enrollment.secret is None:
        logger.warning(
            "Cannot complete TOTP enrollment %s: decryption failed",
            enrollment.id,
        )
        raise_validation_error("errors.mfa.invalid_code", "en")
    if not verify_totp(enrollment.secret, code):
        raise_validation_error("errors.mfa.invalid_code", "en")
    now = _utcnow()
    enrollment.confirmed_at = now
    enrollment.revoked_at = None
    enrollment.is_active = True
    await db.flush()
    return enrollment


async def disable_totp(
    db: AsyncSession,
    *,
    user: User,
    enrollment_id: UUID | None = None,
) -> int:
    stmt = select(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == user.id)
    if enrollment_id is not None:
        stmt = stmt.where(MfaTotpEnrollment.id == enrollment_id)
    result = await db.execute(stmt)
    count = 0
    now = _utcnow()
    for record in result.scalars():
        if record.is_active:
            record.is_active = False
            record.revoked_at = now
            count += 1

    if count > 0:
        await revoke_sessions_matching(
            db=db,
            whereclause=(ActiveSession.user_id == user.id),
        )
    await db.flush()
    return count


async def start_totp_verification(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None = None,
    locale: str | None = None,
    payload: MutableMapping[str, Any] | None = None,
) -> MfaChallenge:
    challenge = await issue_challenge(
        db,
        user_id=user.id,
        session_id=session.id if session else None,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        locale=locale,
        payload=dict(payload or {}),
        attempt_limit=settings.mfa_totp_attempt_limit,
    )
    return challenge


async def verify_totp_for_user(
    db: AsyncSession,
    *,
    user: User,
    code: str,
    challenge_token: str | None = None,
    challenge: MfaChallenge | None = None,
    session_id: UUID | None = None,
    locale: str | None = None,
) -> tuple[MfaTotpEnrollment, MfaChallenge | None]:
    stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.is_active.is_(True))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
    )
    result = await db.execute(stmt)
    enrollments = list(result.scalars())
    if not enrollments and user.mfa_default_method == MFA_METHOD_TOTP:
        legacy_stmt = (
            select(MfaTotpEnrollment)
            .where(MfaTotpEnrollment.user_id == user.id)
            .where(MfaTotpEnrollment.is_active.is_(True))
            .where(MfaTotpEnrollment.revoked_at.is_(None))
            .where(MfaTotpEnrollment.confirmed_at.is_(None))
        )
        legacy_result = await db.execute(legacy_stmt)
        enrollments = list(legacy_result.scalars())
    if not enrollments:
        raise_validation_error("errors.mfa.no_enrollment", locale)
    loaded_challenge = challenge
    if challenge_token and loaded_challenge is None:
        loaded_challenge = await get_challenge(
            db,
            token=challenge_token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            user_id=user.id,
            session_id=session_id,
            locale=locale or "en",
        )
    if loaded_challenge is not None:
        if loaded_challenge.challenge_type != CHALLENGE_TYPE_TOTP_VERIFY:
            raise_validation_error("errors.mfa.invalid_challenge", locale)
        if loaded_challenge.user_id != user.id:
            raise_validation_error("errors.mfa.invalid_challenge", locale)
        if session_id is not None and loaded_challenge.session_id != session_id:
            raise_validation_error("errors.mfa.invalid_challenge", locale)
    limit = _extract_attempt_limit(loaded_challenge, settings.mfa_totp_attempt_limit)
    await _ensure_challenge_not_locked(
        db,
        loaded_challenge,
        method=MFA_METHOD_TOTP,
        limit=limit,
        locale=locale,
    )

    for enrollment in enrollments:
        if enrollment.secret is None:
            logger.warning(
                "Skipping TOTP enrollment %s for user %s: decryption failed",
                enrollment.id,
                user.id,
            )
            continue
        if verify_totp(enrollment.secret, code):
            if loaded_challenge is not None:
                await consume_challenge(
                    db,
                    challenge_token=loaded_challenge.token,
                    challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
                    provided_code=code,
                    provided_method=MFA_METHOD_TOTP,
                    locale=locale,
                )
            return enrollment, loaded_challenge
    await _register_failed_attempt(
        db,
        loaded_challenge,
        method=MFA_METHOD_TOTP,
        limit=limit,
        locale=locale,
    )
    raise_validation_error("errors.mfa.invalid_code", locale)


async def refresh_user_mfa_preferences(
    db: AsyncSession,
    *,
    user: User,
) -> str | None:
    """Re-evaluate the preferred MFA method for a user after factors change."""

    totp_stmt = (
        select(MfaTotpEnrollment.id)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.is_active.is_(True))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .where(MfaTotpEnrollment.confirmed_at.is_not(None))
        .limit(1)
    )
    totp_available = bool((await db.execute(totp_stmt)).scalars().first())

    webauthn_stmt = (
        select(WebAuthnCredential.id)
        .where(WebAuthnCredential.user_id == user.id)
        .limit(1)
    )
    webauthn_available = bool((await db.execute(webauthn_stmt)).scalars().first())

    new_default: str | None
    if webauthn_available:
        new_default = MFA_METHOD_WEBAUTHN
    elif totp_available:
        new_default = MFA_METHOD_TOTP
    else:
        new_default = None

    changed = False
    if user.mfa_default_method != new_default:
        user.mfa_default_method = new_default
        changed = True

    if new_default is not None and not user.mfa_required:
        user.mfa_required = True
        changed = True
    elif new_default is None and user.mfa_required:
        user.mfa_required = False
        changed = True

    if changed:
        await db.flush()

    return new_default


async def reset_user_mfa(db: AsyncSession, *, user: User) -> MfaResetStats:
    """Remove MFA factors, revoke challenges, and clear MFA state for a user."""

    stats = MfaResetStats()

    totp_result = await db.execute(
        delete(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == user.id)
    )
    webauthn_result = await db.execute(
        delete(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )
    challenge_result = await db.execute(
        delete(MfaChallenge).where(MfaChallenge.user_id == user.id)
    )
    recovery_result = await db.execute(
        delete(RecoveryCode).where(RecoveryCode.user_id == user.id)
    )

    stats.totp_deleted = int(totp_result.rowcount or 0)
    stats.webauthn_deleted = int(webauthn_result.rowcount or 0)
    stats.recovery_codes_deleted = int(recovery_result.rowcount or 0)
    stats.challenges_revoked = int(challenge_result.rowcount or 0)

    if user.mfa_required:
        user.mfa_required = False
        stats.fields_cleared = True
    if user.mfa_default_method:
        user.mfa_default_method = None
        stats.fields_cleared = True
    if user.mfa_last_verified_at is not None:
        user.mfa_last_verified_at = None
        stats.fields_cleared = True

    await db.flush()

    # Revoke all sessions globally on MFA reset
    await revoke_sessions_matching(
        db=db,
        whereclause=(ActiveSession.user_id == user.id),
    )

    return stats


async def record_mfa_success(
    db: AsyncSession,
    *,
    user: User,
    session: ActiveSession | None,
    method: str,
) -> None:
    now = _utcnow()
    user.mfa_last_verified_at = now
    if session is not None:
        session.mfa_completed_at = now
        session.mfa_required = False
        session.mfa_method = method[:64]
        session.mfa_verified_at = now
    await db.flush()


async def create_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, datetime]:
    """Issue a new trusted device token for the user."""
    token = secrets.token_urlsafe(48)
    token_hash = _base64url_encode(hashlib.sha256(token.encode("utf-8")).digest())
    now = _utcnow()
    expires_at = now + timedelta(days=settings.trusted_device_expire_days)

    device = TrustedDevice(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        last_used_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
    )
    db.add(device)
    await db.flush()
    return token, expires_at


async def verify_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    token: str,
) -> bool:
    """Check if the provided token is valid for the user."""
    if not token:
        return False

    try:
        token_hash = _base64url_encode(hashlib.sha256(token.encode("utf-8")).digest())
    except Exception:
        return False

    stmt = (
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user.id)
        .where(TrustedDevice.token_hash == token_hash)
    )
    result = await db.execute(stmt)
    device = result.scalars().first()

    if not device:
        return False

    now = _utcnow()
    expires_at = device.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= now:
        # Clean up expired token
        await db.delete(device)
        await db.flush()
        return False

    # Update usage stats
    device.last_used_at = now
    await db.flush()
    return True


async def generate_recovery_codes(db: AsyncSession, *, user: User) -> list[str]:
    """
    Generate a new set of usage-limited recovery codes for the user.
    Existing codes are invalidated.
    """
    # 1. Invalidate existing codes
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    # 2. Generate 10 new codes
    codes: list[str] = []
    for _ in range(10):
        # 10 chars, visually distinct? hex is easiest: 5 bytes = 10 hex chars
        # Or just secrets.token_hex(5).
        # user-facing format: XXXXX-XXXXX?
        # Let's do 10 chars hex.
        raw_code = secrets.token_hex(5)
        formatted = f"{raw_code[:5]}-{raw_code[5:]}".upper()
        codes.append(formatted)

        # Hash
        hashed = get_password_hash(formatted, validate_policy=False)

        db.add(
            RecoveryCode(
                user_id=user.id,
                code_hash=hashed,
                is_used=False,
            )
        )

    await db.flush()
    return codes


async def verify_recovery_code(db: AsyncSession, *, user: User, code: str) -> bool:
    """
    Verify a recovery code. If valid, mark it as used.
    """
    stmt = (
        select(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
        .where(RecoveryCode.is_used.is_(False))
    )
    result = await db.execute(stmt)
    available_codes = result.scalars().all()

    normalized_code = code.strip().upper()

    for record in available_codes:
        if verify_password(normalized_code, record.code_hash):
            record.is_used = True
            record.used_at = _utcnow()
            await db.flush()
            return True

    return False


async def count_remaining_recovery_codes(db: AsyncSession, *, user: User) -> int:
    stmt = (
        select(func.count())
        .select_from(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
        .where(RecoveryCode.is_used.is_(False))
    )
    return (await db.scalar(stmt)) or 0
