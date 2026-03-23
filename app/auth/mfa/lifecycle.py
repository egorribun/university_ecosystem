"""User-level MFA state management — enable/disable/reset/record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, func, select, update

from app.auth.constants import MFA_METHOD_TOTP, MFA_METHOD_WEBAUTHN
from app.models.models import (
    ActiveSession,
    MfaChallenge,
    MfaTotpEnrollment,
    RecoveryCode,
    User,
    WebAuthnCredential,
)
from app.services.session_cleanup import revoke_sessions_matching

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserAuthDTO, UserDTO

import logging

from app.core.logging import get_logger

logger = get_logger(__name__)
audit_logger = logging.getLogger("app.users.audit")


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
                self.totp_deleted > 0,
                self.webauthn_deleted > 0,
                self.recovery_codes_deleted > 0,
                self.challenges_revoked > 0,
                self.fields_cleared,
            )
        )


def user_has_confirmed_interactive_factor(user: User) -> bool:
    """Return True if the user has at least one confirmed interactive factor.

    Security-critical sync helper.  Callers must ensure MFA relationship
    collections are loaded first (e.g. via ensure_mfa_relationships_loaded).
    """
    if getattr(user, "mfa_default_method", None):
        return True

    # Check WebAuthn
    webauthn = getattr(user, "webauthn_credentials", None)
    if webauthn:
        for cred in webauthn:
            if cred is not None:
                return True

    # Check TOTP
    totp = getattr(user, "totp_enrollments", None)
    if totp is not None:
        for enrollment in totp:
            if enrollment:
                confirmed = getattr(enrollment, "confirmed_at", None)
                revoked = getattr(enrollment, "revoked_at", None)
                if confirmed is not None and revoked is None:
                    return True
    return False


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


async def has_webauthn_enabled(db: AsyncSession, user: User) -> bool:
    """Return True if the user has at least one WebAuthn credential."""
    credentials = getattr(user, "webauthn_credentials", None)
    if credentials:
        return True
    else:
        stmt = select(func.count(WebAuthnCredential.id)).where(
            WebAuthnCredential.user_id == user.id
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

    # Check WebAuthn
    credentials = getattr(user, "webauthn_credentials", None)
    if credentials:
        return True
    else:
        # Fallback to DB
        stmt = select(func.count(WebAuthnCredential.id)).where(
            WebAuthnCredential.user_id == user.id
        )
        res = await db.execute(stmt)
        if (res.scalar() or 0) > 0:
            return True

    return False


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

    totp_result = await db.execute(
        delete(MfaTotpEnrollment).where(MfaTotpEnrollment.user_id == target_user_id)
    )
    webauthn_result = await db.execute(
        delete(WebAuthnCredential).where(WebAuthnCredential.user_id == target_user_id)
    )
    challenge_result = await db.execute(
        delete(MfaChallenge).where(MfaChallenge.user_id == target_user_id)
    )
    recovery_result = await db.execute(
        delete(RecoveryCode).where(RecoveryCode.user_id == target_user_id)
    )

    stats.totp_deleted = int(getattr(totp_result, "rowcount", 0))
    stats.webauthn_deleted = int(getattr(webauthn_result, "rowcount", 0))
    stats.recovery_codes_deleted = int(getattr(recovery_result, "rowcount", 0))
    stats.challenges_revoked = int(getattr(challenge_result, "rowcount", 0))

    update_stmt = (
        update(User)
        .where(User.id == target_user_id)
        .where(
            (User.mfa_required)
            | (User.mfa_default_method.is_not(None))
            | (User.mfa_last_verified_at.is_not(None))
        )
        .values(mfa_required=False, mfa_default_method=None, mfa_last_verified_at=None)
    )
    res = await db.execute(update_stmt)
    if getattr(res, "rowcount", 0) > 0:
        stats.fields_cleared = True

    if user:
        user.mfa_required = False
        user.mfa_default_method = None
        user.mfa_last_verified_at = None

    await db.flush()

    await revoke_sessions_matching(
        db=db,
        whereclause=(ActiveSession.user_id == target_user_id),
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
    if not isinstance(user, User):
        updated_user: User | UserAuthDTO | UserDTO = user.model_copy(
            update={"mfa_last_verified_at": now}
        )
    else:
        user.mfa_last_verified_at = now
        updated_user = user

    if session is not None:
        session.mfa_completed_at = now
        session.mfa_required = False
        session.mfa_method = method[:64]
        session.mfa_verified_at = now
    await db.flush()
    return updated_user
