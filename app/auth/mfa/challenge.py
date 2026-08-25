"""MFA challenge issuance, retrieval, consumption, and attempt tracking."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, case, delete, func, literal, or_, select, update

from app.api.validation import raise_http_error
from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_AUTH,
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.email_otp import (
    MfaOtpRejected,
    _digest_message,
    _generate_challenge_token,
    _parse_challenge_id,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.ratelimit import (
    RateLimitExceeded,
    enforce_rate_limit,
    get_default_strategy,
)
from app.models import ActiveSession, MfaChallenge, User
from app.models.auth import ChallengeState
from app.utils.uuid_v7 import generate_uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
audit_logger = logging.getLogger("app.users.audit")
_PENDING_DIGEST = "0" * 64
_APP_DIGEST_KEY_LABEL = "app-primary"

# Re-export so callers that do ``from app.auth.mfa import CHALLENGE_TYPE_TOTP_AUTH`` work.
# (CHALLENGE_TYPE_TOTP_AUTH is already imported from app.auth.constants)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class IssuedChallenge:
    challenge: MfaChallenge
    challenge_token: str

    @property
    def id(self) -> UUID:
        return self.challenge.id

    @property
    def expires_at(self) -> datetime:
        return self.challenge.expires_at

    @property
    def attempt_count(self) -> int:
        return self.challenge.attempt_count

    @property
    def payload(self) -> dict[str, Any] | None:
        return self.challenge.payload


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
    except (TypeError, ValueError):  # RZ-28-01
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


def validate_challenge_binding(
    challenge: MfaChallenge,
    *,
    client_fingerprint: str | None,
    login_session_identifier: str | None,
    active_session_identifier: str | None,
    locale: str = "en",
) -> None:
    expected_session_identifier = (
        active_session_identifier
        if challenge.flow in {"step_up", "email_verification", "email_mfa_enablement"}
        else login_session_identifier
    )
    if (
        client_fingerprint is None
        or expected_session_identifier is None
        or not hmac.compare_digest(client_fingerprint, challenge.client_fingerprint)
        or not hmac.compare_digest(
            expected_session_identifier, challenge.session_identifier
        )
    ):
        raise_http_error(
            status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
        )


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
    challenge.locked_at = challenge.consumed_at
    challenge.state = ChallengeState.LOCKED
    await db.flush()
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
    await db.flush()

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
    flow: str,
    client_fingerprint: str,
    method: str | None = None,
    session_identifier: str,
) -> IssuedChallenge:
    if (
        flow not in {"login", "step_up", "email_verification", "email_mfa_enablement"}
        or not session_identifier
        or len(session_identifier) > 128
        or len(client_fingerprint) != 64
    ):
        raise ValueError("complete MFA challenge binding is required")
    await _enforce_challenge_rate_limit(
        user_id=user_id, challenge_type=challenge_type, locale=locale
    )
    challenge_id = generate_uuid7()
    token = _generate_challenge_token(challenge_id)
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
        id=challenge_id,
        user_id=user_id,
        session_id=session_id,
        challenge_type=challenge_type,
        flow=flow,
        session_identifier=session_identifier,
        client_fingerprint=client_fingerprint,
        method=method
        or (
            MFA_METHOD_RECOVERY_CODE
            if challenge_type == CHALLENGE_TYPE_RECOVERY_CODE
            else MFA_METHOD_TOTP
        ),
        revision=1,
        trust_device_requested=bool(payload_data.get("trust_device", False)),
        token_digest=_PENDING_DIGEST,
        token_key_id=_APP_DIGEST_KEY_LABEL,
        otp_digest=None,
        otp_key_id=None,
        expires_at=expires_at,
        payload=payload_data,
    )
    challenge.token_digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        _digest_message(
            purpose="challenge-token",
            user_id=user_id,
            challenge_id=challenge_id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            method=challenge.method,
            revision=challenge.revision,
            secret_value=token,
        ),
        hashlib.sha256,
    ).hexdigest()
    db.add(challenge)
    await db.flush()
    return IssuedChallenge(challenge=challenge, challenge_token=token)


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
    try:
        challenge_id = _parse_challenge_id(token)
    except MfaOtpRejected:
        raise_http_error(
            status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
        )
        raise ValueError("Invalid challenge") from None
    stmt = select(MfaChallenge).where(MfaChallenge.id == challenge_id)
    if _for_update:
        # A pre-read may already have placed this row in the identity map.
        # Refresh it after waiting for the lock so state such as consumed_at is
        # never evaluated from a stale ORM object.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
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
    expected_digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        _digest_message(
            purpose="challenge-token",
            user_id=challenge.user_id,
            challenge_id=challenge.id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            method=challenge.method,
            revision=challenge.revision,
            secret_value=token,
        ),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_digest, challenge.token_digest):
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
    provided_recovery_code: str | None = None,
    provided_method: str | None = None,
    client_fingerprint: str | None = None,
    login_session_identifier: str | None = None,
    active_session_identifier: str | None = None,
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
        for_update=False,
        locale=locale,
    )

    # Every MFA mutation for one account follows User -> challenge/credential.
    # The pre-read above only discovers the bound account; it acquires no row
    # lock and therefore cannot invert the lock order used by email OTP/TOTP.
    locked_user = (
        (
            await db.execute(
                select(User).where(User.id == challenge.user_id).with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if locked_user is None:
        raise_http_error(
            status.HTTP_400_BAD_REQUEST, "errors.mfa.invalid_challenge", locale
        )
        raise ValueError("Unreachable")
    challenge = await get_challenge(
        db,
        token=challenge_token,
        challenge_type=challenge_type,
        user_id=user_id,
        session_id=session_id,
        consume=False,
        for_update=True,
        locale=locale,
    )

    validate_challenge_binding(
        challenge,
        client_fingerprint=client_fingerprint,
        login_session_identifier=login_session_identifier,
        active_session_identifier=active_session_identifier,
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
        elif challenge.challenge_type == CHALLENGE_TYPE_RECOVERY_CODE:
            v_method = MFA_METHOD_RECOVERY_CODE

    if v_method == MFA_METHOD_TOTP:
        if not provided_code:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )

        from app.auth.mfa.totp import verify_totp_for_user

        await verify_totp_for_user(
            db,
            user=locked_user,
            code=str(provided_code),
            challenge_token=challenge_token,
            challenge=challenge,
            session_id=session_id,
            client_fingerprint=client_fingerprint,
            login_session_identifier=login_session_identifier,
            active_session_identifier=active_session_identifier,
            locale=locale,
        )

    elif v_method == MFA_METHOD_RECOVERY_CODE:
        if challenge.flow not in {"login", "step_up"}:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST,
                "errors.mfa.invalid_challenge",
                locale,
            )
        if not provided_code:
            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.mfa.code_required", locale
            )
        if not await verify_recovery_code(
            db, user=locked_user, code=str(provided_code)
        ):
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

    challenge.consumed_at = _utcnow()
    challenge.state = ChallengeState.CONSUMED
    await db.flush()

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
