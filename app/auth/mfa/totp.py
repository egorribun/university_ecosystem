"""TOTP enrollment, verification, and related challenge helpers."""

from __future__ import annotations

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
from sqlalchemy import delete, func, select, update

from app.api.validation import raise_http_error, raise_validation_error
from app.auth.constants import (
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.challenge import (
    _ensure_challenge_not_locked,
    _extract_attempt_limit,
    _register_failed_attempt,
    get_challenge,
    issue_challenge,
)
from app.auth.mfa.lifecycle import (
    MfaSessionRevocation,
    collect_mfa_session_revocations,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    ActiveSession,
    ChallengeState,
    MfaChallenge,
    MfaTotpEnrollment,
    TrustedDevice,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.mfa.challenge import IssuedChallenge
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


def _ct_verify_totp(secret: str, code: str, *, valid_window: int | None = None) -> bool:
    """P0-W5-02: Constant-time TOTP verification.

    Checks the current window plus ±``valid_window`` windows without
    short-circuiting on a match, eliminating the timing oracle that lets
    attackers distinguish which enrollment slot or window matched.
    """
    return _ct_match_totp_timecode(secret, code, valid_window=valid_window) is not None


def _ct_match_totp_timecode(
    secret: str, code: str, *, valid_window: int | None = None
) -> int | None:
    """Return the matching RFC 6238 counter after evaluating every skew window."""
    window = _TOTP_VALID_WINDOW if valid_window is None else valid_window
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != _TOTP_DIGITS:
        return None
    totp_obj = pyotp.TOTP(secret, digits=_TOTP_DIGITS)
    now = time.time()
    current_timecode = int(now) // int(totp_obj.interval)
    matched_timecodes: list[int] = []
    # Always evaluate all windows — no short-circuit via `or`
    for offset in range(-window, window + 1):
        timecode = current_timecode + offset
        candidate = totp_obj.at(timecode * int(totp_obj.interval))
        if hmac.compare_digest(normalized, candidate):
            matched_timecodes.append(timecode)
    return max(matched_timecodes, default=None)


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
        locked_user = (
            await db.execute(
                select(User)
                .where(User.id == enrollment.user_id)
                .with_for_update(nowait=False)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        locked_enrollment = (
            (
                await db.execute(
                    select(MfaTotpEnrollment)
                    .where(MfaTotpEnrollment.id == enrollment.id)
                    .with_for_update(nowait=False)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )
        if locked_enrollment is None:
            raise_validation_error("errors.mfa.no_enrollment", "en")
        if getattr(locked_enrollment, "secret", None) is None:
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
        if not verify_totp(str(locked_enrollment.secret), code):
            span.set_attribute("mfa.result", "invalid_code")
            span.set_status(Status(StatusCode.ERROR))
            raise_validation_error("errors.mfa.invalid_code", "en")
        now = _utcnow()
        locked_enrollment.confirmed_at = now
        locked_enrollment.revoked_at = None
        locked_enrollment.is_active = True
        locked_user.mfa_epoch = int(locked_user.mfa_epoch or 0) + 1
        await db.execute(
            delete(TrustedDevice).where(TrustedDevice.user_id == locked_user.id)
        )
        await db.flush()
        span.set_attribute("mfa.result", "success")
        span.set_status(Status(StatusCode.OK))
        return locked_enrollment


async def disable_totp(
    db: AsyncSession,
    *,
    user: User,
    enrollment_id: UUID | None = None,
) -> tuple[int, list[MfaSessionRevocation]]:
    locked_user = (
        await db.execute(
            select(User).where(User.id == user.id).with_for_update(nowait=False)
        )
    ).scalar_one()
    stmt = select(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == user.id)
    if enrollment_id is not None:
        stmt = stmt.where(MfaTotpEnrollment.id == enrollment_id)
    result = await db.execute(stmt)
    count = 0
    pending: list[MfaSessionRevocation] = []
    now = _utcnow()
    for record in result.scalars():
        if record.is_active:
            record.is_active = False
            record.revoked_at = now
            count += 1

    if count > 0:
        locked_user.mfa_epoch = int(locked_user.mfa_epoch or 0) + 1
        user.mfa_epoch = locked_user.mfa_epoch
        await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))
        pending = await collect_mfa_session_revocations(
            db,
            user_id=user.id,
        )
    await db.flush()
    return count, pending


async def start_totp_verification(
    db: AsyncSession,
    *,
    user: User | UserAuthDTO | UserDTO,
    session: ActiveSession | None = None,
    locale: str | None = None,
    payload: MutableMapping[str, Any] | None = None,
    flow: str,
    session_identifier: str,
    client_fingerprint: str,
) -> IssuedChallenge:
    with _tracer.start_as_current_span("mfa.totp.challenge.issue"):
        challenge = await issue_challenge(
            db,
            user_id=user.id,
            session_id=session.id if session else None,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            locale=locale,
            payload=dict(payload or {}),
            attempt_limit=settings.mfa_totp_attempt_limit,
            flow=flow,
            session_identifier=session_identifier,
            client_fingerprint=client_fingerprint,
            method=MFA_METHOD_TOTP,
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
    client_fingerprint: str | None = None,
    login_session_identifier: str | None = None,
    active_session_identifier: str | None = None,
    locale: str | None = None,
) -> tuple[MfaTotpEnrollment, MfaChallenge | None]:
    with _tracer.start_as_current_span("mfa.totp.verify") as span:
        span.set_attribute("user.id", str(user.id))
        span.set_attribute("mfa.method", "totp")
        try:
            # Serialize every MFA state transition for one account before
            # touching enrollment or challenge rows.  This preserves the
            # repository-wide User -> enrollment/challenge lock order.
            await db.execute(select(User).where(User.id == user.id).with_for_update())
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
                    for_update=True,
                )
            if loaded_challenge is not None:
                from app.auth.mfa.challenge import validate_challenge_binding

                validate_challenge_binding(
                    loaded_challenge,
                    client_fingerprint=client_fingerprint,
                    login_session_identifier=login_session_identifier,
                    active_session_identifier=active_session_identifier,
                    locale=locale or "en",
                )
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
            matched_timecode: int | None = None
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
                enrollment_timecode = _ct_match_totp_timecode(
                    str(enrollment.secret), code
                )
                if enrollment_timecode is not None and matched_enrollment is None:
                    matched_enrollment = enrollment
                    matched_timecode = enrollment_timecode

            if matched_enrollment is not None and matched_timecode is not None:
                code_hash = hmac.new(
                    settings.secret_key.encode("utf-8"),
                    (
                        f"mfa-totp-replay-v1\x1f{user.id}\x1f"
                        f"{matched_enrollment.id}\x1f{code}"
                    ).encode(),
                    "sha256",
                ).hexdigest()
                # One conditional UPDATE is the replay decision.  It remains
                # correct even when an ORM identity-map object was loaded before
                # a concurrent transaction committed, and it provides the same
                # compare-and-set guarantee on PostgreSQL and SQLite.
                accepted = await db.execute(
                    update(MfaTotpEnrollment)
                    .where(MfaTotpEnrollment.id == matched_enrollment.id)
                    .where(
                        (MfaTotpEnrollment.last_used_timecode.is_(None))
                        | (MfaTotpEnrollment.last_used_timecode < matched_timecode)
                    )
                    .values(
                        last_used_timecode=matched_timecode,
                        last_used_code_hash=code_hash,
                        last_used_at=_utcnow(),
                    )
                    .returning(MfaTotpEnrollment)
                    .execution_options(populate_existing=True)
                )
                locked_enrollment = accepted.scalars().first()
                if locked_enrollment is None:
                    span.set_attribute("mfa.result", "code_already_used")
                    span.set_status(Status(StatusCode.ERROR))
                    raise_validation_error(
                        "errors.mfa.code_already_used", locale or "en"
                    )

                matched_enrollment = (
                    locked_enrollment  # use the locked row for consume_challenge
                )

                if loaded_challenge is not None:
                    loaded_challenge.consumed_at = _utcnow()
                    loaded_challenge.state = ChallengeState.CONSUMED
                    await db.flush()
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
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — sets OTEL error status then re-raises (reviewed TD-27-04)
            # Ensure ERROR status is set for any unexpected exception that wasn't
            # already handled above (e.g. DB errors, unexpected library exceptions).
            span.set_status(Status(StatusCode.ERROR))
            raise
