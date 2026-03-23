"""TOTP enrollment, verification, and related challenge helpers."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pyotp
from fastapi import status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
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
from app.core.logging import get_logger
from app.models.models import ActiveSession, MfaChallenge, MfaTotpEnrollment, User
from app.services.session_cleanup import revoke_sessions_matching

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserAuthDTO, UserDTO

logger = get_logger(__name__)
_tracer = trace.get_tracer(__name__)

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
    return str(pyotp.random_base32(length=length))


def build_totp_uri(secret: str, *, account_name: str, issuer: str | None = None) -> str:
    issuer_name = issuer or settings.mfa_totp_issuer
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    return str(
        totp.provisioning_uri(
            name=account_name, issuer_name=issuer_name or "UniversityEcosystem"
        )
    )


def verify_totp(secret: str, code: str, *, window: int | None = None) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != _TOTP_DIGITS:
        logger.warning(
            "TOTP verification failed: length mismatch",
            extra={
                "event": "mfa.totp.verify_failed",
                "reason": "digit_length_mismatch",
            },
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
            "TOTP verification failed",
            extra={
                "event": "mfa.totp.verify_failed",
                "reason": "invalid_code",
            },
        )
    return bool(result)


def _ct_verify_totp(secret: str, code: str) -> bool:
    """P0-W5-02: Constant-time TOTP verification.

    Checks the current window plus ±1 window (90-second tolerance) without
    short-circuiting on a match, eliminating the timing oracle that lets
    attackers distinguish which enrollment slot or window matched.
    """
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != _TOTP_DIGITS:
        return False
    totp_obj = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    now = time.time()
    matched = False
    # Always evaluate all three windows — no short-circuit via `or`
    for offset in (-30, 0, 30):
        candidate = totp_obj.at(int(now) + offset)
        if hmac.compare_digest(normalized, candidate):
            matched = True
    return matched


async def start_totp_enrollment(
    db: AsyncSession,
    *,
    user: User,
    label: str | None = None,
    reuse_existing: bool = False,
) -> tuple[MfaTotpEnrollment, str, str]:
    # P1-W5-06: Lock the User row to serialize all enrollment operations for this
    # user. SELECT FOR UPDATE on pending enrollments doesn't help when no pending
    # enrollment exists (no rows → no lock), allowing concurrent requests to both
    # find count=0 and both create new enrollments, bypassing MAX_ACTIVE limit.
    await db.execute(select(User).where(User.id == user.id).with_for_update())

    pending_stmt = (
        select(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.user_id == user.id)
        .where(MfaTotpEnrollment.confirmed_at.is_(None))
        .where(MfaTotpEnrollment.revoked_at.is_(None))
        .order_by(MfaTotpEnrollment.created_at.desc())
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
    with _tracer.start_as_current_span("mfa.totp.enroll.complete") as span:
        span.set_attribute("mfa.method", "totp")
        if getattr(enrollment, "secret", None) is None:
            logger.warning(
                "Cannot complete TOTP enrollment: decryption failed",
                extra={
                    "event": "mfa.totp.enroll_failed",
                    "reason": "decryption_failed",
                },
            )
            span.set_attribute("mfa.result", "invalid_code")
            span.set_status(Status(StatusCode.ERROR))
            raise_validation_error("errors.mfa.invalid_code", "en")
        if not verify_totp(str(enrollment.secret), code):
            span.set_attribute("mfa.result", "invalid_code")
            span.set_status(Status(StatusCode.ERROR))
            raise_validation_error("errors.mfa.invalid_code", "en")
        now = _utcnow()
        enrollment.confirmed_at = now
        enrollment.revoked_at = None
        enrollment.is_active = True
        await db.flush()
        span.set_attribute("mfa.result", "success")
        span.set_status(Status(StatusCode.OK))
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
    with _tracer.start_as_current_span("mfa.totp.challenge.issue"):
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
    with _tracer.start_as_current_span("mfa.totp.verify") as span:
        span.set_attribute("user.id", str(user.id))
        span.set_attribute("mfa.method", "totp")
        try:
            # RZ-W8-05: Require a challenge to enable per-code invalidation via
            # consume_challenge(). Without a challenge the same TOTP code can be
            # replayed for the full ±30s window (up to 90 seconds total) because
            # there is no mechanism to mark the code as "already used".
            if not challenge_token and challenge is None:
                raise ValueError(
                    "challenge_token is required for TOTP verification "
                    "(prevents replay attacks within the 90-second TOTP window). "
                    "Call issue_challenge() first and pass the resulting token."
                )
            stmt = (
                select(MfaTotpEnrollment)
                .where(MfaTotpEnrollment.user_id == user.id)
                .where(MfaTotpEnrollment.is_active.is_(True))
                .where(MfaTotpEnrollment.revoked_at.is_(None))
                .where(MfaTotpEnrollment.confirmed_at.is_not(None))
            )
            result = await db.execute(stmt)
            enrollments = list(result.scalars())
            # MED-W19: Removed legacy fallback to unconfirmed enrollments.
            # Only confirmed enrollments (confirmed_at IS NOT NULL) are valid
            # for authentication.  Allowing unconfirmed enrollments was a
            # security regression: a partially-set-up authenticator could be
            # used to authenticate before the user verified ownership of the
            # secret, potentially enabling account takeover if the setup flow
            # was intercepted.
            if not enrollments:
                span.set_attribute("mfa.result", "no_enrollment")
                span.set_status(Status(StatusCode.ERROR))
                raise_validation_error("errors.mfa.no_enrollment", locale or "en")
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
                    span.set_attribute("mfa.result", "invalid_code")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error(
                        "errors.mfa.invalid_challenge", locale or "en"
                    )
                if loaded_challenge.user_id != user.id:
                    span.set_attribute("mfa.result", "invalid_code")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error(
                        "errors.mfa.invalid_challenge", locale or "en"
                    )
                if session_id is not None and loaded_challenge.session_id != session_id:
                    span.set_attribute("mfa.result", "invalid_code")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error(
                        "errors.mfa.invalid_challenge", locale or "en"
                    )
            limit = _extract_attempt_limit(
                loaded_challenge, settings.mfa_totp_attempt_limit
            )
            await _ensure_challenge_not_locked(
                db,
                loaded_challenge,
                method=MFA_METHOD_TOTP,
                limit=limit,
                locale=locale,
            )

            # P0-W5-02: Iterate ALL enrollments unconditionally — no early return on match.
            # This eliminates the timing oracle where returning on the first match leaks
            # which enrollment position held a valid code.
            matched_enrollment: MfaTotpEnrollment | None = None
            for enrollment in enrollments:
                if getattr(enrollment, "secret", None) is None:
                    logger.warning(
                        "Skipping TOTP enrollment: decryption failed",
                        extra={
                            "event": "mfa.totp.enrollment_skipped",
                            "user_id": str(user.id),
                            "reason": "decryption_failed",
                        },
                    )
                    continue
                # Use constant-time comparison — record match but keep iterating
                if (
                    _ct_verify_totp(str(enrollment.secret), code)
                    and matched_enrollment is None
                ):
                    matched_enrollment = enrollment

            if matched_enrollment is not None:
                # RZ-W9-01: Acquire a row-level lock on the enrollment BEFORE reading
                # last_used_code_hash.  Without SELECT FOR UPDATE, two concurrent requests
                # carrying the same TOTP code both see hash=NULL and both pass the replay
                # check before either commits the updated hash, granting double login.
                # nowait=False (blocking) ensures the second request waits for the first to
                # commit, then sees the updated hash and raises code_already_used.
                locked_result = await db.execute(
                    select(MfaTotpEnrollment)
                    .where(MfaTotpEnrollment.id == matched_enrollment.id)
                    .with_for_update(nowait=False)
                )
                locked_enrollment = locked_result.scalars().first()
                if locked_enrollment is None:
                    # Enrollment disappeared between the initial read and the lock — treat
                    # as invalid code rather than letting the request proceed unauthenticated.
                    span.set_attribute("mfa.result", "invalid_code")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error("errors.mfa.invalid_code", locale or "en")

                # MOD-W8-06: Belt-and-suspenders replay prevention (now serialized by lock).
                # Even if the challenge token was consumed by a concurrent request (clock-skew
                # edge case), reject the identical code within the same TOTP window by
                # comparing its SHA-256 hash against the last successfully used code hash.
                code_hash = hashlib.sha256(code.encode()).hexdigest()
                if (
                    locked_enrollment.last_used_code_hash is not None
                    and hmac.compare_digest(
                        locked_enrollment.last_used_code_hash, code_hash
                    )
                ):
                    span.set_attribute("mfa.result", "code_already_used")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error(
                        "errors.mfa.code_already_used", locale or "en"
                    )

                locked_enrollment.last_used_code_hash = code_hash
                locked_enrollment.last_used_at = _utcnow()
                matched_enrollment = (
                    locked_enrollment  # use the locked row for consume_challenge
                )

                if loaded_challenge is not None:
                    await consume_challenge(
                        db,
                        challenge_token=str(loaded_challenge.token),
                        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
                        provided_code=code,
                        provided_method=MFA_METHOD_TOTP,
                        locale=locale or "en",
                    )
                span.set_attribute("mfa.result", "success")
                span.set_status(Status(StatusCode.OK))
                return matched_enrollment, loaded_challenge

            await _register_failed_attempt(
                db,
                loaded_challenge,
                method=MFA_METHOD_TOTP,
                limit=limit,
                locale=locale,
            )
            span.set_attribute("mfa.result", "invalid_code")
            span.set_status(Status(StatusCode.ERROR))
            raise_validation_error("errors.mfa.invalid_code", locale or "en")
        except Exception:
            # Ensure ERROR status is set for any unexpected exception that wasn't
            # already handled above (e.g. DB errors, unexpected library exceptions).
            span.set_status(Status(StatusCode.ERROR))
            raise
