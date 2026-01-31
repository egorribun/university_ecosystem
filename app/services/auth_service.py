import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, Request
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import (
    raise_validation_error,
)
from app.auth.security import get_password_hash, verify_password
from app.core.config import settings
from app.core.localization import resolve_locale
from app.models import models
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.session_cleanup import revoke_sessions_matching
from app.tasks.email import send_auth_email
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES, send_reset_email

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    """
    Hash a token using HMAC-SHA256 with the app's SECRET_KEY.

    Using HMAC provides defense-in-depth by binding the hash to the
    application secret, preventing precomputed rainbow table attacks
    even if the database is compromised.
    """
    return hmac.new(
        settings.secret_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


def _send_reset_email_blocking(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    send_reset_email(to_email, link, full_name, locale=locale)


# Removed local _send_reset_email in favor of TaskIQ task


async def _prepare_password_reset_token(
    db: AsyncSession,
    user: models.User,
    *,
    token_hash: str,
    expires_at: datetime,
) -> None:
    max_active = max(1, int(settings.password_reset_max_active_tokens))
    result = await db.execute(
        select(models.PasswordResetToken)
        .where(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used.is_(False),
        )
        .order_by(
            models.PasswordResetToken.created_at.desc(),
            models.PasswordResetToken.id.desc(),
        )
    )
    active_tokens = list(result.scalars())

    for stale in active_tokens[max_active:]:
        stale.used = True

    if len(active_tokens) >= max_active:
        target = active_tokens[max_active - 1]
        target.token_hash = token_hash
        target.expires_at = expires_at
        target.used = False
        target.created_at = datetime.now(UTC)
        return

    record = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        used=False,
    )
    db.add(record)


async def _create_email_change_request(
    db: AsyncSession, user: models.User, new_email: str
) -> tuple[models.EmailChangeToken, str]:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

    await db.execute(
        update(models.EmailChangeToken)
        .where(
            models.EmailChangeToken.user_id == user.id,
            models.EmailChangeToken.used.is_(False),
        )
        .values(used=True)
    )

    record = models.EmailChangeToken(
        user_id=user.id,
        new_email=new_email,
        token_hash=token_hash,
        expires_at=expires,
        used=False,
    )
    db.add(record)
    await db.flush()
    return record, token


async def _get_active_email_change_request(
    db: AsyncSession, user_id: int
) -> models.EmailChangeToken | None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(models.EmailChangeToken)
        .where(
            models.EmailChangeToken.user_id == user_id,
            models.EmailChangeToken.used.is_(False),
            models.EmailChangeToken.expires_at > now,
        )
        .order_by(models.EmailChangeToken.created_at.desc())
    )
    return result.scalars().first()


async def attach_pending_email(
    db: AsyncSession, user: models.User | None
) -> models.User | None:
    if user is None:
        return None
    pending = await _get_active_email_change_request(db, user.id)
    user.pending_email = pending.new_email if pending else None
    return user


class AuthService:
    def __init__(self, db: AsyncSession, audit: AuditService) -> None:
        self.db = db
        self.audit = audit

    async def initiate_password_reset(
        self,
        email: str,
        request: Request,
        bg: BackgroundTasks,
    ) -> None:
        normalized_email = email.strip().lower()
        result = await self.db.execute(
            select(models.User).where(func.lower(models.User.email) == normalized_email)
        )
        user = result.scalar_one_or_none()
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = _hash_token(token)
            expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
            await _prepare_password_reset_token(
                self.db,
                user,
                token_hash=token_hash,
                expires_at=expires,
            )
            await self.db.commit()
            base = settings.app_base_url_clean
            reset_link = f"{base}/reset-password?token={token}"
            locale = resolve_locale(request=request, user=user)
            await send_auth_email.kiq(
                user.email,
                reset_link,
                user.full_name or "",
                locale,
            )
            self.audit.log(
                "password.reset.initiated",
                request,
                user_id=user.id,
                reason="initiated",
            )
        else:
            self.audit.log(
                "password.reset.initiated",
                request,
                level=logging.WARNING,
                reason="user_not_found",
            )

    async def perform_password_reset(
        self,
        token: str,
        new_password: str,
        request: Request,
    ) -> None:
        locale = resolve_locale(request=request)
        token_hash = _hash_token(token)
        result = await self.db.execute(
            select(models.PasswordResetToken).where(
                models.PasswordResetToken.token_hash == token_hash,
                models.PasswordResetToken.used.is_(False),
            )
        )
        rec = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if not rec:
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                reason="token_invalid",
            )
            raise_validation_error(
                locale,
                "errors.password.invalid_or_expired_link",
            )
        expires_at = rec.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                user_id=rec.user_id,
                reason="token_expired",
            )
            raise_validation_error(
                locale,
                "errors.password.invalid_or_expired_link",
            )
        user = await self.db.get(models.User, rec.user_id)
        if not user or not getattr(user, "is_active", True):
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                user_id=rec.user_id,
                reason="user_inactive",
            )
            raise_validation_error(locale, "errors.password.invalid_link")
        try:
            user.hashed_password = get_password_hash(new_password, locale=locale)
        except ValueError as exc:
            raise_validation_error(locale, "errors.common.bad_request", str(exc))
        rec.used = True
        await self.db.execute(
            update(models.PasswordResetToken)
            .where(
                models.PasswordResetToken.user_id == rec.user_id,
                models.PasswordResetToken.used.is_(False),
            )
            .values(used=True)
        )
        await self.db.commit()
        self.audit.log(
            "password.reset.completed",
            request,
            user_id=rec.user_id,
            reason="completed",
        )

    async def initiate_email_change(
        self,
        user: models.User,
        payload: schemas.UserEmailChangeIn,
        request: Request,
        bg: BackgroundTasks,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        if not verify_password(payload.password, user.hashed_password):
            raise_validation_error(locale, "errors.users.invalid_password")

        normalized_email = str(payload.email).strip().lower()
        adapter = TypeAdapter(EmailStr)
        try:
            validated_email = adapter.validate_python(normalized_email)
        except ValueError:
            raise_validation_error(locale, "errors.users.invalid_email")

        if validated_email == user.email:
            raise_validation_error(locale, "errors.users.email_same")

        existing = await self.db.execute(
            select(models.User.id).where(
                func.lower(models.User.email) == validated_email,
                models.User.id != user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise_validation_error(locale, "errors.users.email_in_use")

        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        _, token = await _create_email_change_request(self.db, db_user, validated_email)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)

        # Also attach to the current user object if it's different instance
        if user is not db_user:
            await attach_pending_email(self.db, user)

        base = settings.app_base_url_clean
        confirm_link = f"{base}/settings/email-confirm?token={token}"
        await send_auth_email.kiq(
            validated_email,
            confirm_link,
            user.full_name or "",
            locale,
        )

        self.audit.log(
            "users.email.change_requested",
            request,
            user_id=user.id,
            reason="pending_confirmation",
            extra={"email": validated_email},
        )
        return db_user

    async def confirm_email_change(
        self,
        user: models.User,
        token: str,
        request: Request,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        token_hash = _hash_token(token)
        now = datetime.now(UTC)

        result = await self.db.execute(
            select(models.EmailChangeToken).where(
                models.EmailChangeToken.token_hash == token_hash
            )
        )
        record = result.scalar_one_or_none()
        if record is None or record.user_id != user.id or record.used:
            raise_validation_error(
                locale,
                "errors.users.email_confirmation_invalid",
            )

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise_validation_error(
                locale,
                "errors.users.email_confirmation_invalid",
            )

        existing = await self.db.execute(
            select(models.User.id).where(
                func.lower(models.User.email) == record.new_email,
                models.User.id != user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            record.used = True
            await self.db.execute(
                update(models.EmailChangeToken)
                .where(
                    models.EmailChangeToken.user_id == user.id,
                    models.EmailChangeToken.id != record.id,
                )
                .values(used=True)
            )
            await self.db.commit()
            await attach_pending_email(self.db, user)
            raise_validation_error(
                locale,
                "errors.users.email_confirmation_conflict",
            )

        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        db_user.email = record.new_email
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(models.EmailChangeToken.id == record.id)
            .values(used=True)
        )
        await self.db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user.id,
                models.EmailChangeToken.id != record.id,
            )
            .values(used=True)
        )

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)
        if user is not db_user:
            await attach_pending_email(self.db, user)

        # Update current user object as well for immediate response
        user.email = record.new_email

        self.audit.log(
            "users.email.changed",
            request,
            user_id=user.id,
            reason="confirmed",
            extra={"email": record.new_email},
        )
        return db_user

    async def change_password(
        self,
        user: models.User,
        payload: schemas.UserPasswordChangeIn,
        request: Request,
    ) -> tuple[bool, list[models.ActiveSession]]:
        locale = resolve_locale(request=request, user=user)
        if not verify_password(payload.current_password, user.hashed_password):
            raise_validation_error(locale, "errors.users.invalid_password")
        if verify_password(payload.new_password, user.hashed_password):
            raise_validation_error(locale, "errors.users.password_same")
        try:
            hashed_password = get_password_hash(payload.new_password, locale=locale)
        except ValueError as exc:
            raise_validation_error(locale, "errors.common.bad_request", str(exc))

        db_user = await self.db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        db_user.hashed_password = hashed_password

        active_session: models.ActiveSession | None = getattr(
            request.state, "active_session", None
        )
        current_session_id = active_session.id if active_session else None
        conditions = [
            models.ActiveSession.user_id == user.id,
            models.ActiveSession.revoked_at.is_(None),
        ]
        if current_session_id is not None:
            conditions.append(models.ActiveSession.id != current_session_id)
        revoked = await revoke_sessions_matching(
            db=self.db, whereclause=and_(*conditions)
        )

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)

        # Update current user object
        user.hashed_password = hashed_password

        self.audit.log(
            "users.password.changed",
            request,
            user_id=user.id,
            reason="user_update",
            extra={"revoked_sessions": revoked},
        )
        return True, revoked

    async def refresh_pending_email(
        self, user: models.User | None
    ) -> models.User | None:
        """
        Refresh the pending_email field on the user model.
        """
        if user is None:
            return None
        pending = await _get_active_email_change_request(self.db, user.id)
        user.pending_email = pending.new_email if pending else None
        return user
