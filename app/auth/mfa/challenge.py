"""MFA challenge issuance, retrieval, consumption, and attempt tracking."""

from __future__ import annotations

import json
import logging
from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pyotp
from fastapi import status
from sqlalchemy import and_, case, delete, func, literal, or_, select, update

from app.api.validation import raise_http_error
from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_AUTH,
    CHALLENGE_TYPE_TOTP_VERIFY,
    CHALLENGE_TYPE_WEBAUTHN_AUTH,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.ratelimit import (
    RateLimitExceeded,
    enforce_rate_limit,
    get_default_strategy,
)
from app.models import ActiveSession, MfaChallenge, MfaTotpEnrollment, User
from app.models.auth import ChallengeState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
audit_logger = logging.getLogger("app.users.audit")

# Re-export so callers that do ``from app.auth.mfa import CHALLENGE_TYPE_TOTP_AUTH`` work.
# (CHALLENGE_TYPE_TOTP_AUTH is already imported from app.auth.constants)


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    try:
        await enforce_rate_limit(
            identifier=key,
            limit=limit,
            window_seconds=window,
            strategy=get_default_strategy("mfa"),
        )
    except RateLimitExceeded:
        raise_http_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "errors.rate_limit.generic",
            locale or "en",
        )


def _extract_attempt_limit(
    challenge: MfaChallenge | None, fallback: int | None = None
) -> int | None:
    limit = fallback
    payload = getattr(challenge, "payload", None)
    if challenge and payload and hasattr(payload, "get"):
        raw_limit = payload.get("attempt_limit")
        if isinstance(raw_limit, int):
            limit = raw_limit
    if limit is None:
        return None
    try:
        resolved = int(limit)
    except (TypeError, ValueError):# RZ-28-01
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
                "challenge_id": challenge.id,
            },
            default=str,
        )
    )
    raise_http_error(
        status_code,
        "errors.auth.mfa_challenge_locked",
        locale or "en",
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
    """P1-W5-05: Atomic attempt increment + conditional lock via UPDATE…RETURNING.

    Replaces the non-atomic read-then-write pattern that allowed concurrent
    requests to see the same attempt_count, each incrementing independently,
    resulting in the lock threshold being exceeded without actually locking.
    PostgreSQL serializes concurrent UPDATEs to the same row — no race window.
    """
    if challenge is None:
        return

    # Single atomic statement: increment + conditionally set locked_at
    stmt = (
        update(MfaChallenge)
        .where(
            MfaChallenge.id == challenge.id,
            MfaChallenge.consumed_at.is_(None),
            MfaChallenge.locked_at.is_(None),
        )
        .values(
            attempt_count=MfaChallenge.attempt_count + 1,
            locked_at=case(
                (
                    and_(
                        literal(limit).isnot(None),
                        MfaChallenge.attempt_count + 1 >= limit,
                    ),
                    func.now(),
                ),
                else_=None,
            ),
            # TD-W5-01: Keep explicit state in sync with locked_at.
            # PostgreSQL requires explicit CAST for enum-typed columns in
            # CASE expressions — bare text/varchar is rejected with
            # "column is of type challenge_state_enum but expression is of
            # type text" (asyncpg DatatypeMismatchError).
            # Using literal().cast(column.type) emits proper
            # CAST('locked' AS challenge_state_enum) in the generated SQL.
            state=case(
                (
                    and_(
                        literal(limit).isnot(None),
                        MfaChallenge.attempt_count + 1 >= limit,
                    ),
                    literal(ChallengeState.LOCKED.value).cast(MfaChallenge.state.type),
                ),
                else_=literal(ChallengeState.PENDING.value).cast(
                    MfaChallenge.state.type
                ),
            ),
        )
        .returning(MfaChallenge.attempt_count, MfaChallenge.locked_at)
    )
    row = (await db.execute(stmt)).one_or_none()
    await db.commit()

    if row is None:
        # Challenge was already consumed or locked by a concurrent request — no-op
        return

    _new_count, locked_at = row
    if locked_at is not None:
        # Just locked by this very update — raise the appropriate error
        raise_http_error(
            status_code,
            "errors.auth.mfa_challenge_locked",
            locale or "en",
        )


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
    import secrets as _secrets

    token = _secrets.token_urlsafe(48)
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


async def issue_dummy_challenge(db: AsyncSession) -> None:
    """
    Perform a generic DB write to normalize response times and mitigate
    user enumeration timing attacks.
    """
    from sqlalchemy import text

    # Updating a massive table with an unknown ID takes 0.01ms because PostgreSQL
    # uses the PK index and finds no row. This does NOT successfully normalize
    # the timing against an actual I/O-heavy update.
    # Instead, we execute a deterministic delay representing the 95th percentile
    # of a legitimate User update (e.g. ~10ms).
    await db.execute(text("SELECT pg_sleep(0.01)"))
    await db.flush()


async def get_challenge(
    db: AsyncSession,
    *,
    token: str,
    challenge_type: str | list[str],
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    consume: bool = False,
    locale: str = "en",
    for_update: bool = False,  # MED-W19: only acquire row lock when actually needed
) -> MfaChallenge:
    # MED-W19: Apply with_for_update() only when consume=True (or explicitly
    # requested).  Unconditional SELECT FOR UPDATE on read-only lookups causes
    # unnecessary lock contention on the MfaChallenge table.
    _for_update = for_update or consume
    stmt = select(MfaChallenge).where(MfaChallenge.token == token)
    if _for_update:
        stmt = stmt.with_for_update()
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
        raise ValueError("Invalid challenge")
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
        challenge.state = ChallengeState.CONSUMED
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
    from app.auth.mfa.recovery import (
        verify_recovery_code,  # avoid circular at module level
    )

    challenge = await get_challenge(
        db,
        token=challenge_token,
        challenge_type=challenge_type,
        user_id=user_id,
        session_id=session_id,
        consume=False,
        for_update=True,  # TD-W5-01: Acquire lock to prevent race conditions
        locale=locale,
    )

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
        if not user:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
            )
            raise ValueError("Unreachable")
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
            totp = pyotp.TOTP(str(enrollment.secret))
            if totp.verify(str(provided_code), valid_window=1):
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
        if not provided_code:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )
        user = await db.get(User, challenge.user_id)
        if not user:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
            )
            raise ValueError("Unreachable")
        if not await verify_recovery_code(db, user=user, code=str(provided_code)):
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
        if not user:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
            )
            raise ValueError("Unreachable")
        try:
            # P2-W5-20: Strict type checks on the DB-stored payload to prevent
            # type confusion. A non-dict payload (or non-dict "options") would
            # silently produce an empty challenge string, bypassing verification.
            raw_payload = challenge.payload
            if not isinstance(raw_payload, dict):
                raise TypeError("WebAuthn challenge payload must be a dict")
            options = raw_payload.get("options")
            if not isinstance(options, dict):
                raise TypeError("WebAuthn challenge options must be a dict")
            challenge_str = options.get("challenge")
            if not isinstance(challenge_str, str) or not challenge_str:
                raise TypeError("WebAuthn challenge value must be a non-empty string")
            await service.verify_authentication(
                user,
                challenge_str,
                provided_webauthn_response,
            )
        except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — registers failed attempt then raises HTTP error (reviewed TD-27-04)
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

    challenge.consumed_at = _utcnow()
    challenge.state = ChallengeState.CONSUMED
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
    return int(getattr(result, "rowcount", 0))
