"""User-level MFA state management — enable/disable/reset/record."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import delete, func, inspect, select, update  # MED-W19

from app.auth.constants import MFA_METHOD_EMAIL_OTP, MFA_METHOD_TOTP
from app.models import (
    ActiveSession,
    MfaChallenge,
    MfaTotpEnrollment,
    RecoveryCode,
    TrustedDevice,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserAuthDTO, UserDTO

from redis.exceptions import RedisError

from app.core.logging import get_logger

logger = get_logger(__name__)
audit_logger = logging.getLogger("app.users.audit")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MfaResetStats:
    totp_deleted: int = 0
    trusted_devices_revoked: int = 0
    recovery_codes_deleted: int = 0
    challenges_revoked: int = 0
    fields_cleared: bool = False
    session_revocations: list[MfaSessionRevocation] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(
            (
                self.totp_deleted > 0,
                self.trusted_devices_revoked > 0,
                self.recovery_codes_deleted > 0,
                self.challenges_revoked > 0,
                self.fields_cleared,
            )
        )


@dataclass(frozen=True, slots=True)
class MfaSessionRevocation:
    """Redis revocation to publish only after the DB transaction commits."""

    jti: str
    expires_at: datetime


async def collect_mfa_session_revocations(
    db: AsyncSession,
    *,
    user_id: UUID,
    current_session_id: UUID | None = None,
) -> list[MfaSessionRevocation]:
    """Collect durable session revocations without external side effects."""
    stmt = (
        select(ActiveSession)
        .where(ActiveSession.user_id == user_id)
        .where(ActiveSession.revoked_at.is_(None))
        .with_for_update(nowait=False)
    )
    if current_session_id is not None:
        stmt = stmt.where(ActiveSession.id != current_session_id)
    result = await db.execute(stmt)
    now = _utcnow()
    pending: list[MfaSessionRevocation] = []
    for sibling in result.scalars():
        sibling.revoked_at = now
        sibling.signing_key = secrets.token_urlsafe(32)
        pending.append(
            MfaSessionRevocation(
                jti=str(sibling.jti),
                expires_at=sibling.expires_at,
            )
        )
    await db.flush()
    return pending


async def revoke_sibling_sessions_for_factor_change(
    db: AsyncSession,
    *,
    user_id: UUID,
    current_session_id: UUID,
) -> list[MfaSessionRevocation]:
    """Revoke every other session while preserving the ceremony session."""
    return await collect_mfa_session_revocations(
        db,
        user_id=user_id,
        current_session_id=current_session_id,
    )


async def publish_mfa_session_revocations(
    pending: list[MfaSessionRevocation],
) -> None:
    """Publish Redis tombstones after the authoritative DB commit succeeds."""
    if not pending:
        return
    from app.auth.redis_session import get_session_backend

    try:
        backend = await get_session_backend()
        for revocation in pending:
            await backend.revoke_session(
                revocation.jti,
                expires_at=revocation.expires_at,
            )
    except (RuntimeError, RedisError, OSError):
        logger.exception(
            "Failed to publish MFA factor-change session revocations; "
            "database revocation remains authoritative"
        )


def user_has_confirmed_interactive_factor(user: User) -> bool:
    """Return True if the user has at least one confirmed interactive factor.

    Security-critical sync helper.  Callers must ensure MFA relationship
    collections are loaded first (e.g. via ensure_mfa_relationships_loaded).
    """
    # MED-W19: Raise an explicit error if the totp_enrollments relationship has
    # not been loaded.  Previously the function silently returned False when the
    # collection was an unloaded SQLAlchemy lazy attribute, masking MFA bypass
    # bugs (a user with TOTP enabled would appear to have no factor).
    try:
        insp = inspect(user)
        loaded_value = insp.attrs["totp_enrollments"].loaded_value
        # NEVER_SET is the sentinel used by SQLAlchemy when the attribute has
        # not been populated at all (neither eagerly loaded nor explicitly set).
        from sqlalchemy.orm.base import NEVER_SET

        if loaded_value is NEVER_SET:
            raise RuntimeError(
                f"user_has_confirmed_interactive_factor() called with "
                f"totp_enrollments not loaded on User(id={user.id}). "
                f"Load the relationship before calling this function."
            )
    except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — re-raises RuntimeError, swallows ORM inspection errors (reviewed TD-27-04)
        # Re-raise only our own RuntimeError; ignore inspection errors for
        # non-ORM objects (e.g. DTOs used in tests).
        if isinstance(exc, RuntimeError):
            raise

    # Check TOTP
    totp = getattr(user, "totp_enrollments", None)
    if totp is not None:
        for enrollment in totp:
            if enrollment:
                confirmed = getattr(enrollment, "confirmed_at", None)
                revoked = getattr(enrollment, "revoked_at", None)
                if confirmed is not None and revoked is None:
                    return True
    return isinstance(getattr(user, "email_mfa_enabled_at", None), datetime)


async def has_totp_enabled(db: AsyncSession, user: User) -> bool:
    """Return True if the user has at least one active TOTP enrollment."""
    enrollments = getattr(user, "totp_enrollments", None)
    if enrollments:
        for e in enrollments:
            if e.confirmed_at is not None and e.revoked_at is None:
                return True
    else:
        stmt = select(func.count(MfaTotpEnrollment.id)).where(
            MfaTotpEnrollment.user_id == user.id,
            MfaTotpEnrollment.confirmed_at.is_not(None),
            MfaTotpEnrollment.revoked_at.is_(None),
        )
        res = await db.execute(stmt)
        if (res.scalar() or 0) > 0:
            return True
    return False


async def user_has_active_factor(db: AsyncSession, user: User) -> bool:
    """Return True if the user has any active MFA factor."""
    # Check TOTP
    enrollments = getattr(user, "totp_enrollments", None)
    if enrollments:  # Use truthiness to check if list is non-empty
        for e in enrollments:
            if e.is_active and e.revoked_at is None:
                return True
    else:
        # Fallback to DB if collection is empty or not loaded
        stmt = select(func.count(MfaTotpEnrollment.id)).where(
            MfaTotpEnrollment.user_id == user.id,
            MfaTotpEnrollment.is_active.is_(True),
            MfaTotpEnrollment.revoked_at.is_(None),
        )
        res = await db.execute(stmt)
        if (res.scalar() or 0) > 0:
            return True

    return isinstance(getattr(user, "email_mfa_enabled_at", None), datetime)


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

    email_otp_available = user.email_mfa_enabled_at is not None

    new_default: str | None
    if totp_available:
        new_default = MFA_METHOD_TOTP
    elif email_otp_available:
        new_default = MFA_METHOD_EMAIL_OTP
    else:
        new_default = None

    new_required = new_default is not None
    changed = (
        user.mfa_default_method != new_default or user.mfa_required != new_required
    )

    if changed:
        # Use an explicit UPDATE so this works regardless of which session owns
        # the `user` object (e.g. when `user` was loaded via a different Depends
        # session than the dishka-provided `db`).
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(mfa_default_method=new_default, mfa_required=new_required)
        )
        # Keep the in-memory object consistent for the remainder of this request.
        user.mfa_default_method = new_default
        user.mfa_required = new_required

    return new_default


async def disable_email_mfa(
    db: AsyncSession, *, user: User
) -> list[MfaSessionRevocation]:
    """Disable verified-email MFA and revoke state derived from the old epoch."""
    locked_user = (
        await db.execute(
            select(User).where(User.id == user.id).with_for_update(nowait=False)
        )
    ).scalar_one()
    locked_user.email_mfa_enabled_at = None
    await refresh_user_mfa_preferences(db, user=locked_user)
    locked_user.mfa_epoch = int(locked_user.mfa_epoch or 0) + 1
    await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))
    pending = await collect_mfa_session_revocations(
        db,
        user_id=user.id,
    )
    user.email_mfa_enabled_at = None
    user.mfa_default_method = locked_user.mfa_default_method
    user.mfa_required = locked_user.mfa_required
    user.mfa_epoch = locked_user.mfa_epoch
    await db.flush()
    return pending


async def reset_user_mfa(
    db: AsyncSession, *, user: User | None = None, user_id: UUID | str | None = None
) -> MfaResetStats:
    """Remove MFA factors, revoke challenges, and clear MFA state for a user."""
    target_user_id: Any = user_id
    if user:
        target_user_id = user.id
    elif user_id is None:
        raise ValueError("Either user or user_id must be provided")

    stats = MfaResetStats()

    locked_user = (
        await db.execute(
            select(User).where(User.id == target_user_id).with_for_update(nowait=False)
        )
    ).scalar_one_or_none()
    previous_epoch = int(locked_user.mfa_epoch or 0) if locked_user else 0

    totp_result = await db.execute(
        delete(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == target_user_id)
    )
    trusted_result = await db.execute(
        delete(TrustedDevice).where(TrustedDevice.user_id == target_user_id)
    )
    challenge_result = await db.execute(
        delete(MfaChallenge).where(MfaChallenge.user_id == target_user_id)
    )
    recovery_result = await db.execute(
        delete(RecoveryCode).where(RecoveryCode.user_id == target_user_id)
    )

    stats.totp_deleted = int(getattr(totp_result, "rowcount", 0))
    stats.trusted_devices_revoked = int(getattr(trusted_result, "rowcount", 0))
    stats.recovery_codes_deleted = int(getattr(recovery_result, "rowcount", 0))
    stats.challenges_revoked = int(getattr(challenge_result, "rowcount", 0))
    update_stmt = (
        update(User)
        .where(User.id == target_user_id)
        .values(
            mfa_required=False,
            mfa_default_method=None,
            mfa_last_verified_at=None,
            email_mfa_enabled_at=None,
            mfa_epoch=User.mfa_epoch + 1,
        )
    )
    res = await db.execute(update_stmt)
    if getattr(res, "rowcount", 0) > 0:
        stats.fields_cleared = True

    if user:
        user.mfa_required = False
        user.mfa_default_method = None
        user.mfa_last_verified_at = None
        user.email_mfa_enabled_at = None
        user.mfa_epoch = previous_epoch + 1
        user.trusted_devices = []

    await db.flush()

    stats.session_revocations = await collect_mfa_session_revocations(
        db,
        user_id=target_user_id,
    )

    return stats


async def record_mfa_success(
    db: AsyncSession,
    *,
    user: User | UserAuthDTO | UserDTO,
    session: ActiveSession | None,
    method: str,
) -> User | UserAuthDTO | UserDTO:
    now = _utcnow()
    if not isinstance(user, User) and session is None:
        # DTO-only callers use this helper to shape an authenticated response.
        # With no durable session there is no database epoch to synchronize.
        updated_dto: User | UserAuthDTO | UserDTO = user.model_copy(
            update={"mfa_last_verified_at": now}
        )
        await db.flush()
        return updated_dto

    user_id = user.id
    epoch_result = await db.execute(select(User.mfa_epoch).where(User.id == user_id))
    current_epoch = epoch_result.scalar_one_or_none()
    if current_epoch is None:
        raise RuntimeError("Cannot record MFA success for a missing user")

    if not isinstance(user, User):
        updated_user: User | UserAuthDTO | UserDTO = user.model_copy(
            update={
                "mfa_last_verified_at": now,
                "mfa_epoch": int(current_epoch),
            }
        )
    else:
        user.mfa_last_verified_at = now
        user.mfa_epoch = int(current_epoch)
        updated_user = user

    await db.execute(
        update(User).where(User.id == user_id).values(mfa_last_verified_at=now)
    )

    if session is not None:
        session_update = cast(
            "CursorResult[Any]",
            await db.execute(
                update(ActiveSession)
                .where(ActiveSession.id == session.id)
                .where(ActiveSession.user_id == user_id)
                .where(ActiveSession.revoked_at.is_(None))
                .values(
                    mfa_completed_at=now,
                    mfa_required=False,
                    mfa_method=method[:64],
                    mfa_verified_at=now,
                    mfa_epoch=int(current_epoch),
                )
            ),
        )
        if session_update.rowcount != 1:
            raise RuntimeError("Cannot record MFA success for an inactive session")

        # Mirror the committed values onto the request-scoped instance. It may
        # be detached or owned by FastAPI's dependency session while `db` is a
        # separate Dishka session, so persistence must not depend on this write.
        session.mfa_completed_at = now
        session.mfa_required = False
        session.mfa_method = method[:64]
        session.mfa_verified_at = now
        # Factor changes advance the account epoch.  Keep only the session that
        # performed the fresh-MFA ceremony usable; sibling sessions retain the
        # prior epoch and fail the next authorization check.
        session.mfa_epoch = int(current_epoch)
    await db.flush()
    return updated_user
