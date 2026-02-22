"""TOTP enrollment, verification, and related challenge helpers."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pyotp
from fastapi import status
from sqlalchemy import func, select

from app.api.validation import raise_http_error, raise_validation_error
from app.auth.constants import (
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.challenge import (
    _ensure_challenge_not_locked,
    _extract_attempt_limit,
    _register_failed_attempt,
    consume_challenge,
    get_challenge,
    issue_challenge,
)
from app.core.config import settings
from app.models.models import ActiveSession, MfaChallenge, MfaTotpEnrollment, User
from app.services.session_cleanup import revoke_sessions_matching

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserAuthDTO, UserDTO

logger = logging.getLogger(__name__)

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


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        otpauth_url = build_totp_uri(
            str(pending.secret), account_name=str(account_name)
        )
        return pending, str(pending.secret), otpauth_url

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
    otpauth_url = build_totp_uri(secret, account_name=str(account_name))
    return enrollment, secret, otpauth_url


async def complete_totp_enrollment(
    db: AsyncSession,
    *,
    enrollment: MfaTotpEnrollment,
    code: str,
) -> MfaTotpEnrollment:
    if enrollment.secret is None:
        logger.warning(  # type: ignore[unreachable]
            "Cannot complete TOTP enrollment %s: decryption failed",
            enrollment.id,
        )
        raise_validation_error("errors.mfa.invalid_code", "en")
        raise ValueError("Invalid code")
    if not verify_totp(str(enrollment.secret), code):
        raise_validation_error("errors.mfa.invalid_code", "en")
        raise ValueError("Invalid code")
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
    user: User | UserAuthDTO | UserDTO,
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
        raise_validation_error("errors.mfa.no_enrollment", locale or "en")
        raise ValueError("No enrollment")
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
            raise_validation_error("errors.mfa.invalid_challenge", locale or "en")
            raise ValueError("Invalid challenge")
        if loaded_challenge.user_id != user.id:
            raise_validation_error("errors.mfa.invalid_challenge", locale or "en")
            raise ValueError("Invalid challenge")
        if session_id is not None and loaded_challenge.session_id != session_id:
            raise_validation_error("errors.mfa.invalid_challenge", locale or "en")
            raise ValueError("Invalid challenge")
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
            logger.warning(  # type: ignore[unreachable]
                "Skipping TOTP enrollment %s for user %s: decryption failed",
                enrollment.id,
                user.id,
            )
            continue
        if verify_totp(str(enrollment.secret), code):
            if loaded_challenge is not None:
                await consume_challenge(
                    db,
                    challenge_token=str(loaded_challenge.token),
                    challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
                    provided_code=code,
                    provided_method=MFA_METHOD_TOTP,
                    locale=locale or "en",
                )
            return enrollment, loaded_challenge
    await _register_failed_attempt(
        db,
        loaded_challenge,
        method=MFA_METHOD_TOTP,
        limit=limit,
        locale=locale,
    )
    raise_validation_error("errors.mfa.invalid_code", locale or "en")
    raise ValueError("Invalid code")
