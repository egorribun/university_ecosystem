from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar, cast

from fastapi import BackgroundTasks, Request
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import exc as orm_exc
from sqlalchemy import inspect

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession
    from app.models import models as _models
    from app.schemas.dtos import UserAuthDTO

    _AnyUser = _models.User | UserAuthDTO | UserDTO

from app.api.validation import raise_validation_error
from app.auth.security import (
    _validate_password_hibp,
    get_password_hash,
    verify_password,
)
from app.schemas.dtos import UserDTO
from app.core.config import settings
from app.core.exceptions.domain import EntityNotFound
from app.core.localization import resolve_locale
from app.core.protocols import UserLike
from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.repositories.auth_repository import AuthRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.tasks.email import send_auth_email
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

# _UserT is used for functions that return the same type as passed in
_UserT = TypeVar("_UserT", bound=UserLike)

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        audit: AuditService,
        auth_repo: AuthRepository,
        user_repo: UserRepository,
        session_repo: SessionRepository,
    ) -> None:
        self.audit = audit
        self.auth_repo = auth_repo
        self.user_repo = user_repo
        self.session_repo = session_repo

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
            await send_auth_email.kick(  # type: ignore[attr-defined]
                str(user.email),
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
            from app.auth.security import _validate_password_hibp

            # HIBP check must be done before hashing (async, network call)
            await _validate_password_hibp(new_password, locale=locale)
            new_hashed = await get_password_hash(new_password, locale=locale)
            await self.user_repo.update(rec.user_id, {"hashed_password": new_hashed})
        except ValueError as exc:
            raise_validation_error("errors.common.bad_request", locale, reason=str(exc))

        # Mark token as used via repository
        await self.auth_repo.mark_password_reset_token_used(rec.id)

        # Invalidate all other active tokens for this user
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
        user: models.User | UserAuthDTO,
        payload: schemas.UserEmailChangeIn,
        request: Request,
        bg: BackgroundTasks,
    ) -> models.User | UserAuthDTO | UserDTO:
        locale = resolve_locale(request=request, user=user)
        from app.auth.security import verify_password

        if not await verify_password(payload.password, str(user.hashed_password)):
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

        if not hasattr(db_user, "model_dump"):  # Check if it's NOT a Pydantic DTO
            await self.auth_repo.refresh(db_user)

        loaded_user = await ensure_mfa_relationships_loaded(self.auth_repo.db, db_user)
        enriched_user = await attach_pending_email(self.auth_repo.db, loaded_user)

        if user is not enriched_user:
            await attach_pending_email(self.auth_repo.db, user)

        base = settings.app_base_url_clean
        confirm_link = f"{base}/settings/email-confirm?token={token}"
        await send_auth_email.kick(  # type: ignore[attr-defined]
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
        from typing import cast

        return cast(models.User | UserDTO, enriched_user)

    async def confirm_email_change(
        self,
        user: models.User | UserAuthDTO | UserDTO,
        token: str,
        request: Request,
    ) -> models.User | UserAuthDTO | UserDTO:
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

        if await self.user_repo.check_email_exists(
            str(record.new_email), exclude_user_id=user.id
        ):
            await self.auth_repo.mark_email_change_token_used(record.id)
            await self.auth_repo.invalidate_other_email_change_tokens(
                user.id, exclude_token_id=record.id
            )

            await self.auth_repo.commit()
            await attach_pending_email(self.auth_repo.db, user)
            raise_validation_error(
                "errors.users.email_confirmation_conflict",
                locale,
            )

        db_user = await self.user_repo.update(
            record.user_id, {"email": record.new_email}
        )
        if not db_user:
            raise EntityNotFound("User", record.user_id)

        await self.auth_repo.mark_email_change_token_used(record.id)
        await self.auth_repo.invalidate_other_email_change_tokens(
            user.id, exclude_token_id=record.id
        )

        await self.auth_repo.commit()
        await ensure_mfa_relationships_loaded(self.auth_repo.db, db_user)
        await attach_pending_email(self.auth_repo.db, db_user)

        if user is not db_user:
            await attach_pending_email(self.auth_repo.db, user)

        self.audit.log(
            "users.email.changed",
            request,
            user_id=user.id,
            reason="confirmed",
        )
        return db_user

    async def change_password(
        self,
        user: models.User | UserAuthDTO,
        payload: schemas.UserPasswordChangeIn,
        request: Request,
    ) -> tuple[bool, int]:
        locale = resolve_locale(request=request, user=user)

        if not await verify_password(
            payload.current_password, str(user.hashed_password)
        ):
            raise_validation_error("errors.users.invalid_password", locale)
        if await verify_password(payload.new_password, str(user.hashed_password)):
            raise_validation_error("errors.users.password_same", locale)

        try:
            await _validate_password_hibp(payload.new_password, locale=locale)
            hashed_password = await get_password_hash(
                payload.new_password, locale=locale
            )
        except ValueError as exc:
            raise_validation_error("errors.common.bad_request", locale, reason=str(exc))

        await self.user_repo.update(user.id, {"hashed_password": hashed_password})

        active_session: models.ActiveSession | None = getattr(
            request.state, "active_session", None
        )
        current_session_id = active_session.id if active_session else None

        if current_session_id is not None:
            revoked = await self.session_repo.revoke_all_except(
                user_id=user.id, current_session_id=current_session_id
            )
        else:
            revoked = await self.session_repo.revoke_all_for_user(user_id=user.id)

        await self.auth_repo.commit()

        if isinstance(user, models.User):
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
        self, user: models.User | UserAuthDTO | UserDTO | None
    ) -> models.User | UserAuthDTO | UserDTO | None:
        if user is None:
            return None

        pending = await self.auth_repo.get_active_email_change_request(user.id)
        email = pending.new_email if pending else None

        return cast("_AnyUser | None", attach_pending_email_sync(user, email))


def _hash_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


async def attach_pending_email(
    db: AsyncSession, user: _AnyUser | None
) -> _AnyUser | None:
    if user is None:
        return None

    if isinstance(user, models.User):
        try:
            insp = inspect(user)
            if insp is not None and "email_change_tokens" not in insp.unloaded:
                return cast("_AnyUser", attach_pending_email_sync(user, None))
        except orm_exc.DetachedInstanceError:
            # Expected: object is detached from its session (e.g. in a background
            # task).  Fall through to the DB query path below.
            pass
        except Exception:
            # Unexpected inspect error — log but do not propagate so that the
            # caller still gets a result.  (RZ-6: audit 2026-02-24)
            logger.warning(
                "attach_pending_email: unexpected inspect error for user %s",
                getattr(user, "id", "unknown"),
                exc_info=True,
            )

    repo = AuthRepository(db)
    pending = await repo.get_active_email_change_request(user.id)
    email = pending.new_email if pending else None

    return cast("_AnyUser | None", attach_pending_email_sync(user, email))


def attach_pending_email_sync(user: Any, email: str | None) -> Any:
    if hasattr(user, "model_copy"):
        from typing import cast

        # (audit 2026-02-24) use string for cast to avoid runtime NameError
        # as UserDTO is only available under TYPE_CHECKING.
        return cast(Any, user).model_copy(update={"pending_email": email})

    if email is not None:
        user.pending_email = email
    elif isinstance(user, models.User):
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
        pending = tokens[0] if tokens else None
        user.pending_email = pending.new_email if pending else None

    return user
