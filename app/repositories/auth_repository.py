from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import models
from app.repositories.base import BaseRepository
from app.schemas import schemas


class AuthRepository(
    BaseRepository[models.PasswordResetToken, schemas.PasswordResetTokenCreate, dict]
):
    """Repository for Authentication-related tokens (Password Reset, Email Change)."""

    @property
    def model(self) -> type[models.PasswordResetToken]:
        return models.PasswordResetToken

    async def create_password_reset_token(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> models.PasswordResetToken:
        """
        Create a password reset token, ensuring max active tokens limit.
        """
        max_active = max(1, int(settings.password_reset_max_active_tokens))

        # Get current active tokens
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
        )
        active_tokens = list(result.scalars())

        # Invalidate excess tokens
        for stale in active_tokens[max_active:]:
            stale.used = True

        # Recycle existing token slot if at limit
        if len(active_tokens) >= max_active:
            target = active_tokens[max_active - 1]
            target.token_hash = token_hash
            target.expires_at = expires_at
            target.used = False
            target.created_at = datetime.now(UTC)
            return target

        # Create new token
        record = models.PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_valid_password_reset_token(
        self, token_hash: str, with_for_update: bool = False
    ) -> models.PasswordResetToken | None:
        """
        Get a valid (unused) password reset token by hash.
        """
        stmt = select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == token_hash,
            models.PasswordResetToken.used.is_(False),
        )
        if with_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_password_reset_token_used(self, token_id: int) -> None:
        """Mark a password reset token as used."""
        await self.db.execute(
            update(models.PasswordResetToken)
            .where(models.PasswordResetToken.id == token_id)
            .values(used=True)
        )

    async def invalidate_all_user_password_reset_tokens(self, user_id: int) -> None:
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
        self, user_id: int, new_email: str, token_hash: str, expires_at: datetime
    ) -> models.EmailChangeToken:
        """
        Create an email change token, invalidating previous unused ones.
        """
        # Invalidate existing unused tokens
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user_id,
                models.EmailChangeToken.used.is_(False),
            )
            .values(used=True)
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
        return record

    async def get_active_email_change_request(
        self, user_id: int
    ) -> models.EmailChangeToken | None:
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
        return result.scalars().first()

    async def get_valid_email_change_token(
        self, token_hash: str, with_for_update: bool = False
    ) -> models.EmailChangeToken | None:
        """Get a valid (unused) email change token by hash."""
        stmt = select(models.EmailChangeToken).where(
            models.EmailChangeToken.token_hash == token_hash,
        )
        if with_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_email_change_token_used(self, token_id: int) -> None:
        """Mark an email change token as used."""
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(models.EmailChangeToken.id == token_id)
            .values(used=True)
        )

    async def invalidate_other_email_change_tokens(
        self, user_id: int, exclude_token_id: int
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

    # WebAuthn Credential Methods

    async def get_webauthn_credential(
        self, user_id: int, credential_id: str
    ) -> models.WebAuthnCredential | None:
        """Get a specific WebAuthn credential for a user."""
        stmt = select(models.WebAuthnCredential).where(
            models.WebAuthnCredential.user_id == user_id,
            models.WebAuthnCredential.credential_id == credential_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_webauthn_credentials(
        self, user_id: int
    ) -> list[models.WebAuthnCredential]:
        """List all WebAuthn credentials for a user."""
        stmt = select(models.WebAuthnCredential).where(
            models.WebAuthnCredential.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_webauthn_credential(self, **kwargs) -> models.WebAuthnCredential:
        """Create a new WebAuthn credential."""
        record = models.WebAuthnCredential(**kwargs)
        self.db.add(record)
        await self.db.flush()
        return record

    # Login and MFA Methods

    async def record_login_history(self, **kwargs) -> models.LoginHistory:
        """Create a new login history record."""
        record = models.LoginHistory(**kwargs)
        self.db.add(record)
        return record

    async def get_user_mfa_capabilities(self, user_id: int) -> dict[str, bool]:
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

        webauthn_stmt = (
            select(mfa.WebAuthnCredential.id)
            .where(mfa.WebAuthnCredential.user_id == user_id)
            .limit(1)
        )
        result = await self.db.execute(webauthn_stmt)
        webauthn_exists = bool(result.scalars().first())

        return {
            mfa.MFA_METHOD_TOTP: totp_exists,
            mfa.MFA_METHOD_WEBAUTHN: webauthn_exists,
        }

    async def has_active_mfa(self, user_id: int) -> bool:
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

    async def create_failed_attempt(self, **kwargs) -> models.FailedLoginAttempt:
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
        return int(result.rowcount or 0)


def get_auth_repository(db: AsyncSession) -> AuthRepository:
    return AuthRepository(db)
