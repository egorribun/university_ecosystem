from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import BackgroundTasks, Request
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import and_

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import (
    raise_validation_error,
)
from app.auth.security import (
    _validate_password_hibp,
    get_password_hash,
    verify_password,
)
from app.core.config import settings
from app.core.exceptions.domain import EntityNotFound
from app.core.localization import resolve_locale
from app.models import models
from app.models.user_loaders import (
    ensure_mfa_relationships_loaded,
)
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.session_cleanup import revoke_sessions_matching
from app.tasks.email import send_auth_email
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        audit: AuditService,
        auth_repo: AuthRepository,
        user_repo: UserRepository,
    ) -> None:
        self.audit = audit
        self.auth_repo = auth_repo
        self.user_repo = user_repo

    async def initiate_password_reset(
        self,
        email: str,
        request: Request,
        bg: BackgroundTasks,
    ) -> None:
        user = await self.user_repo.get_by_email(email)
        start = time.perf_counter()
        from app.core.timing import ensure_minimum_time

        if user:
            # Re-fetch with profile to ensure we have full name for email
            # Although get_by_email tries to load MFA options, we need profile for name.
            # user_repo.get_by_email includes USER_MFA_LOAD_OPTIONS which includes
            # profile joinedload.
            pass

        if user:
            token = secrets.token_urlsafe(32)
            token_hash = _hash_token(token)
            expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

            await self.auth_repo.create_password_reset_token(
                user_id=user.id, token_hash=token_hash, expires_at=expires
            )

            await self.auth_repo.commit()
            base = settings.app_base_url_clean
            reset_link = f"{base}/reset-password?token={token}"
            locale = resolve_locale(request=request, user=user)
            await send_auth_email.kiq(
                user.email,
                reset_link,
                user.profile.full_name if user.profile else "",
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

        await ensure_minimum_time(start, settings.auth_min_response_time)

    async def perform_password_reset(
        self,
        token: str,
        new_password: str,
        request: Request,
    ) -> None:
        locale = resolve_locale(request=request)
        token_hash = _hash_token(token)

        # Use repository to fetch valid token with lock
        rec = await self.auth_repo.get_valid_password_reset_token(
            token_hash, with_for_update=True
        )

        now = datetime.now(UTC)
        if not rec:
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                reason="token_invalid",
            )
            raise_validation_error(
                "errors.password.invalid_or_expired_link",
                locale,
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
                "errors.password.invalid_or_expired_link",
                locale,
            )

        user = await self.user_repo.get(rec.user_id)
        if not user or not getattr(user, "is_active", True):
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                user_id=rec.user_id,
                reason="user_inactive",
            )
            raise_validation_error("errors.password.invalid_link", locale)

        try:
            # HIBP check must be done before hashing (async, network call)
            await _validate_password_hibp(new_password, locale=locale)
            user.hashed_password = await get_password_hash(new_password, locale=locale)
        except ValueError as exc:
            raise_validation_error("errors.common.bad_request", locale, reason=str(exc))

        # Mark token as used via repository
        await self.auth_repo.mark_password_reset_token_used(rec.id)

        # Invalidate other active tokens for this user?
        # Requirement usually says: invalidate all others? Or just this one?
        # Standard: invalidate all others to be safe.
        await self.auth_repo.invalidate_all_user_password_reset_tokens(user.id)

        await self.auth_repo.commit()
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
        if not await verify_password(payload.password, user.hashed_password):
            raise_validation_error("errors.users.invalid_password", locale)

        normalized_email = str(payload.email).strip().lower()
        adapter = TypeAdapter(EmailStr)
        try:
            validated_email = adapter.validate_python(normalized_email)
        except ValueError:
            raise_validation_error("errors.users.invalid_email", locale)

        if validated_email == user.email:
            raise_validation_error("errors.users.email_same", locale)

        if await self.user_repo.check_email_exists(
            validated_email, exclude_user_id=user.id
        ):
            raise_validation_error("errors.users.email_in_use", locale)

        # Refetch user to ensure we have latest state and correct context
        db_user = await self.user_repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

        await self.auth_repo.create_email_change_token(
            user_id=db_user.id,
            new_email=validated_email,
            token_hash=token_hash,
            expires_at=expires,
        )

        await self.auth_repo.commit()
        await self.auth_repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.auth_repo.db, db_user)
        await attach_pending_email(self.auth_repo.db, db_user)

        # Also attach to the current user object if it's different instance
        if user is not db_user:
            await attach_pending_email(self.auth_repo.db, user)

        base = settings.app_base_url_clean
        confirm_link = f"{base}/settings/email-confirm?token={token}"
        await send_auth_email.kiq(
            validated_email,
            confirm_link,
            user.profile.full_name if user.profile else "",
            locale,
        )

        self.audit.log(
            "users.email.change_requested",
            request,
            user_id=user.id,
            reason="pending_confirmation",
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

        record = await self.auth_repo.get_valid_email_change_token(
            token_hash, with_for_update=True
        )

        if record is None or record.user_id != user.id or record.used:
            raise_validation_error(
                "errors.users.email_confirmation_invalid",
                locale,
            )

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise_validation_error(
                "errors.users.email_confirmation_invalid",
                locale,
            )

        # Race condition check: is email taken by someone else now?
        if await self.user_repo.check_email_exists(
            record.new_email, exclude_user_id=user.id
        ):
            # Mark as used to prevent further attempts? Or just fail?
            # Logic says conflict.
            # We should invalidate this token as it point to invalid email now?
            # Or just error out and let user try again / expire.
            # Current logic: mark as used and conflict error.

            await self.auth_repo.mark_email_change_token_used(record.id)
            # And invalidate others?
            await self.auth_repo.invalidate_other_email_change_tokens(
                user.id, exclude_token_id=record.id
            )

            await self.auth_repo.commit()
            await attach_pending_email(self.auth_repo.db, user)
            raise_validation_error(
                "errors.users.email_confirmation_conflict",
                locale,
            )

        db_user = await self.user_repo.get(user.id)
        db_user.email = record.new_email

        # Mark this token as used
        await self.auth_repo.mark_email_change_token_used(record.id)
        # Invalidate all other pending requests for this user
        await self.auth_repo.invalidate_other_email_change_tokens(
            user.id, exclude_token_id=record.id
        )

        await self.auth_repo.commit()
        await self.auth_repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.auth_repo.db, db_user)
        await attach_pending_email(self.auth_repo.db, db_user)
        if user is not db_user:
            await attach_pending_email(self.auth_repo.db, user)

        # Update current user object as well for immediate response
        user.email = record.new_email

        self.audit.log(
            "users.email.changed",
            request,
            user_id=user.id,
            reason="confirmed",
        )
        return db_user

    async def change_password(
        self,
        user: models.User,
        payload: schemas.UserPasswordChangeIn,
        request: Request,
    ) -> tuple[bool, list[models.ActiveSession]]:
        locale = resolve_locale(request=request, user=user)
        if not await verify_password(payload.current_password, user.hashed_password):
            raise_validation_error("errors.users.invalid_password", locale)
        if await verify_password(payload.new_password, user.hashed_password):
            raise_validation_error("errors.users.password_same", locale)
        try:
            # HIBP check must be done before hashing (async, network call)
            await _validate_password_hibp(payload.new_password, locale=locale)
            hashed_password = await get_password_hash(
                payload.new_password, locale=locale
            )
        except ValueError as exc:
            raise_validation_error("errors.common.bad_request", locale, reason=str(exc))

        db_user = await self.user_repo.get(user.id)
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
            db=self.auth_repo.db, whereclause=and_(*conditions)
        )

        await self.auth_repo.commit()
        await self.auth_repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.auth_repo.db, db_user)

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
        pending = await self.auth_repo.get_active_email_change_request(user.id)
        user.pending_email = pending.new_email if pending else None
        return user


# Private helpers were removed as their logic moved to AuthRepository
# But some are still used locally or need to be imported if we want to use them.

# `_hash_token` is still used in this file.


def _hash_token(token: str) -> str:
    """
    Hash a token using HMAC-SHA256 with the app's SECRET_KEY.
    """
    return hmac.new(
        settings.secret_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


async def attach_pending_email(
    db: AsyncSession, user: models.User | None
) -> models.User | None:
    """Attach the pending email to a user, loading the relationship if needed."""
    if user is None:
        return None

    from sqlalchemy import inspect

    insp = inspect(user)
    if "email_change_tokens" in insp.unloaded:
        # Fall back to repo call
        repo = AuthRepository(db)
        pending = await repo.get_active_email_change_request(user.id)
        user.pending_email = pending.new_email if pending else None
        return user

    return attach_pending_email_sync(user)


def attach_pending_email_sync(
    user: models.User | None,
) -> models.User | None:
    """Attach the pending email to a user whose email_change_tokens are already loaded."""
    if user is None:
        return None
    now = datetime.now(UTC)
    tokens = [
        t
        for t in user.email_change_tokens
        if not t.used
        and (
            t.expires_at.replace(tzinfo=UTC)
            if t.expires_at.tzinfo is None
            else t.expires_at
        )
        > now
    ]
    tokens.sort(key=lambda x: x.created_at, reverse=True)
    user.pending_email = tokens[0].new_email if tokens else None
    return user
