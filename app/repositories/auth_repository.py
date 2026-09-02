from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

import app.models as models
from app.core.config import settings
from app.core.protocols import AsyncDatabaseSession
from app.repositories.base import BaseRepository
from app.schemas import schemas
from app.schemas.dtos import EmailChangeTokenDTO, PasswordResetTokenDTO


class AuthRepository(
    BaseRepository[
        models.PasswordResetToken,
        PasswordResetTokenDTO,
        schemas.PasswordResetTokenCreate,
        dict[str, Any],
    ]
):
    """Repository for Authentication-related tokens (Password Reset, Email Change)."""

    # Removed redundant __init__ override to use BaseRepository.db correctly.
    # (Fix for AttributeError: 'AuthRepository' object has no attribute 'db')

    @property
    def model(self) -> type[models.PasswordResetToken]:
        return models.PasswordResetToken

    @property
    def dto_class(self) -> type[PasswordResetTokenDTO]:
        return PasswordResetTokenDTO

    async def create_password_reset_token(
        self,
        user_id: uuid.UUID | str,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetTokenDTO:
        """
        Create a password reset token, ensuring max active tokens limit.
        """
        max_active = max(1, int(settings.password_reset_max_active_tokens))

        # DB-1 (audit 2026-03): Use SELECT FOR UPDATE so that concurrent
        # password-reset requests for the same user_id serialise here instead
        # of racing through the read-check-modify pattern and creating N tokens.
        result = await self.db.execute(
            select(models.PasswordResetToken)
            .where(
                models.PasswordResetToken.user_id == user_id,
                models.PasswordResetToken.used.is_(False),
            )
            .order_by(
                models.PasswordResetToken.created_at.desc(),
                models.PasswordResetToken.id.desc(),
            )
            .with_for_update()
        )
        active_tokens = list(result.scalars())

        # PERF-5: Bulk UPDATE stale tokens in one round-trip instead of N individual
        # attribute assignments that each emit their own UPDATE statement.
        if len(active_tokens) > max_active:
            stale_ids = [t.id for t in active_tokens[max_active:]]
            await self.db.execute(
                update(models.PasswordResetToken)
                .where(models.PasswordResetToken.id.in_(stale_ids))
                .values(used=True)
                .execution_options(synchronize_session="fetch")
            )

        # Recycle existing token slot if at limit
        if len(active_tokens) >= max_active:
            target = active_tokens[max_active - 1]
            target.token_hash = token_hash
            target.expires_at = expires_at
            target.used = False
            target.created_at = datetime.now(UTC)
            # HIGH-W19: flush recycled token mutations so DB sees the changes
            # within this transaction, matching the create path below
            await self.db.flush()
            return self._to_dto(target)

        # Create new token
        record = models.PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False,
        )
        self.db.add(record)
        await self.db.flush()
        return PasswordResetTokenDTO.model_validate(record)

    async def get_valid_password_reset_token(
        self, token_hash: str, with_for_update: bool = False
    ) -> PasswordResetTokenDTO | None:
        """
        Get a valid (unused, non-expired) password reset token by hash.

        RZ-NEW-02 (audit 2026-03): expires_at filter added — previously a
        consumed-but-not-yet-GCed token with a past expiry could be accepted
        by callers that only checked ``used=False`` without re-validating the
        timestamp themselves.
        """
        now = datetime.now(UTC)
        stmt = select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == token_hash,
            models.PasswordResetToken.used.is_(False),
            models.PasswordResetToken.expires_at > now,
        )
        if with_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return PasswordResetTokenDTO.model_validate(obj) if obj else None

    async def mark_password_reset_token_used(self, token_id: uuid.UUID | str) -> None:
        """Mark a password reset token as used."""
        await self.db.execute(
            update(models.PasswordResetToken)
            .where(models.PasswordResetToken.id == token_id)
            .values(used=True)
        )

    async def invalidate_all_user_password_reset_tokens(
        self, user_id: uuid.UUID | str
    ) -> None:
        """Invalidate all password reset tokens for a user."""
        await self.db.execute(
            update(models.PasswordResetToken)
            .where(
                models.PasswordResetToken.user_id == user_id,
                models.PasswordResetToken.used.is_(False),
            )
            .values(used=True)
        )

    # Email Change Token Methods

    async def create_email_change_token(
        self,
        user_id: uuid.UUID | str,
        new_email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailChangeTokenDTO:
        """
        Create an email change token, invalidating previous unused ones.

        RZ-NEW-03 (audit 2026-03): SELECT FOR UPDATE added before the
        invalidation UPDATE so that two concurrent email-change requests for
        the same user serialise here instead of both passing the "no active
        token" check and inserting duplicate rows (TOCTOU fix, mirrors the
        pattern already used in create_password_reset_token).
        """
        # Lock existing active tokens for this user so concurrent requests queue
        # behind this transaction rather than racing through the UPDATE+INSERT.
        await self.db.execute(
            select(models.EmailChangeToken.id)
            .where(
                models.EmailChangeToken.user_id == user_id,
                models.EmailChangeToken.used.is_(False),
            )
            .with_for_update()
        )

        await self.db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user_id,
                models.EmailChangeToken.used.is_(False),
            )
            .values(used=True)
            .execution_options(synchronize_session="fetch")
        )

        record = models.EmailChangeToken(
            user_id=user_id,
            new_email=new_email,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False,
        )
        self.db.add(record)
        await self.db.flush()
        return EmailChangeTokenDTO.model_validate(record)

    async def get_active_email_change_request(
        self, user_id: uuid.UUID | str
    ) -> EmailChangeTokenDTO | None:
        """Get the latest active email change request for a user."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user_id,
                models.EmailChangeToken.used.is_(False),
                models.EmailChangeToken.expires_at > now,
            )
            .order_by(models.EmailChangeToken.created_at.desc())
        )
        obj = result.scalars().first()
        return EmailChangeTokenDTO.model_validate(obj) if obj else None

    async def get_valid_email_change_token(
        self, token_hash: str, with_for_update: bool = False
    ) -> EmailChangeTokenDTO | None:
        """Get a valid (unused, non-expired) email change token by hash.

        RZ-F-01 (audit 2026-03-07): Added used=False and expires_at > now
        filters — without them, consumed or expired tokens could be replayed
        for account takeover. Mirrors the fix in get_valid_password_reset_token
        (RZ-NEW-02, audit 2026-03-06 wave 3).
        """
        now = datetime.now(UTC)
        stmt = select(models.EmailChangeToken).where(
            models.EmailChangeToken.token_hash == token_hash,
            models.EmailChangeToken.used.is_(False),
            models.EmailChangeToken.expires_at > now,
        )
        if with_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return EmailChangeTokenDTO.model_validate(obj) if obj else None

    async def mark_email_change_token_used(self, token_id: uuid.UUID | str) -> None:
        """Mark an email change token as used."""
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(models.EmailChangeToken.id == token_id)
            .values(used=True)
        )

    async def invalidate_other_email_change_tokens(
        self, user_id: uuid.UUID | str, exclude_token_id: uuid.UUID | str
    ) -> None:
        """Invalidate all other email change tokens for a user."""
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user_id,
                models.EmailChangeToken.id != exclude_token_id,
            )
            .values(used=True)
        )

    # Login and MFA Methods

    async def record_login_history(self, **kwargs: Any) -> models.LoginHistory:
        """Create a new login history record."""
        record = models.LoginHistory(**kwargs)
        self.db.add(record)
        return record

    async def get_user_mfa_capabilities(
        self, user_id: uuid.UUID | str
    ) -> dict[str, bool]:
        """Detect which MFA factors are active for a user."""
        from app.auth import mfa

        totp_stmt = (
            select(mfa.MfaTotpEnrollment.id)
            .where(
                mfa.MfaTotpEnrollment.user_id == user_id,
                mfa.MfaTotpEnrollment.is_active.is_(True),
                mfa.MfaTotpEnrollment.revoked_at.is_(None),
            )
            .limit(1)
        )
        result = await self.db.execute(totp_stmt)
        totp_exists = bool(result.scalars().first())

        user = await self.db.get(models.User, user_id)
        email_otp_available = bool(
            user is not None and user.email_mfa_enabled_at is not None
        )

        return {
            mfa.MFA_METHOD_TOTP: totp_exists,
            mfa.MFA_METHOD_EMAIL_OTP: email_otp_available,
        }

    async def has_active_mfa(self, user_id: uuid.UUID | str) -> bool:
        """Return True if the user has any active MFA factor."""
        capabilities = await self.get_user_mfa_capabilities(user_id)
        return any(capabilities.values())

    # Lockout Methods

    async def get_failed_attempts(
        self, email: str, limit: int
    ) -> list[models.FailedLoginAttempt]:
        """Fetch recent failed login attempts."""
        stmt = (
            select(models.FailedLoginAttempt)
            .where(models.FailedLoginAttempt.email == email)
            .order_by(models.FailedLoginAttempt.attempted_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def prune_stale_failed_attempts(self, email: str, cutoff: datetime) -> None:
        """Delete stale failed login attempts."""
        from sqlalchemy import delete

        await self.db.execute(
            delete(models.FailedLoginAttempt)
            .where(models.FailedLoginAttempt.email == email)
            .where(models.FailedLoginAttempt.attempted_at < cutoff)
        )

    async def create_failed_attempt(self, **kwargs: Any) -> models.FailedLoginAttempt:
        """Register a new failed login attempt."""
        record = models.FailedLoginAttempt(**kwargs)
        self.db.add(record)
        await self.db.flush()
        return record

    async def clear_failed_attempts(self, email: str) -> int:
        """Clear all failed login attempts for an email."""

        from sqlalchemy import delete

        result = await self.db.execute(
            delete(models.FailedLoginAttempt).where(
                models.FailedLoginAttempt.email == email
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)


def get_auth_repository(db: AsyncDatabaseSession) -> AuthRepository:
    return AuthRepository(db)
