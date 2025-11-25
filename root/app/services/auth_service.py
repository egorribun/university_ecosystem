import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import anyio
from fastapi import BackgroundTasks, HTTPException, Request, status
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash, verify_password
from app.core.config import settings
from app.localization import resolve_locale, translate
from app.models import models
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.session_cleanup import revoke_sessions_matching
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES, send_reset_email

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_reset_email_blocking(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    send_reset_email(to_email, link, full_name, locale=locale)


async def _send_reset_email(
    to_email: str, link: str, full_name: str = "", locale: str | None = None
) -> None:
    await anyio.to_thread.run_sync(
        _send_reset_email_blocking,
        to_email,
        link,
        full_name,
        locale,
    )


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
    setattr(user, "pending_email", pending.new_email if pending else None)
    return user


class AuthService:
    def __init__(self, audit: AuditService):
        self.audit = audit

    async def initiate_password_reset(
        self,
        db: AsyncSession,
        email: str,
        request: Request,
        bg: BackgroundTasks,
    ) -> None:
        normalized_email = email.strip().lower()
        result = await db.execute(
            select(models.User).where(func.lower(models.User.email) == normalized_email)
        )
        user = result.scalar_one_or_none()
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = _hash_token(token)
            expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
            await _prepare_password_reset_token(
                db,
                user,
                token_hash=token_hash,
                expires_at=expires,
            )
            await db.commit()
            base = settings.app_base_url_clean
            reset_link = f"{base}/reset-password?token={token}"
            locale = resolve_locale(request=request, user=user)
            bg.add_task(
                _send_reset_email,
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
        db: AsyncSession,
        token: str,
        new_password: str,
        request: Request,
    ) -> None:
        locale = resolve_locale(request=request)
        token_hash = _hash_token(token)
        result = await db.execute(
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate(
                    "errors.password.invalid_or_expired_link", locale=locale
                ),
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate(
                    "errors.password.invalid_or_expired_link", locale=locale
                ),
            )
        user = await db.get(models.User, rec.user_id)
        if not user or not getattr(user, "is_active", True):
            self.audit.log(
                "password.reset.failed",
                request,
                level=logging.WARNING,
                user_id=rec.user_id,
                reason="user_inactive",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.password.invalid_link", locale=locale),
            )
        try:
            user.hashed_password = get_password_hash(new_password, locale=locale)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        rec.used = True
        await db.execute(
            update(models.PasswordResetToken)
            .where(
                models.PasswordResetToken.user_id == rec.user_id,
                models.PasswordResetToken.used.is_(False),
            )
            .values(used=True)
        )
        await db.commit()
        self.audit.log(
            "password.reset.completed",
            request,
            user_id=rec.user_id,
            reason="completed",
        )

    async def initiate_email_change(
        self,
        db: AsyncSession,
        user: models.User,
        payload: schemas.UserEmailChangeIn,
        request: Request,
        bg: BackgroundTasks,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        if not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.invalid_password", locale=locale),
            )

        normalized_email = str(payload.email).strip().lower()
        adapter = TypeAdapter(EmailStr)
        try:
            validated_email = adapter.validate_python(normalized_email)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.invalid_email", locale=locale),
            ) from exc

        if validated_email == user.email:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.email_same", locale=locale),
            )

        existing = await db.execute(
            select(models.User.id).where(
                func.lower(models.User.email) == validated_email,
                models.User.id != user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.email_in_use", locale=locale),
            )

        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        _, token = await _create_email_change_request(db, db_user, validated_email)

        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        await attach_pending_email(db, db_user)

        # Also attach to the current user object if it's different instance
        if user is not db_user:
            await attach_pending_email(db, user)

        base = settings.app_base_url_clean
        confirm_link = f"{base}/settings/email-confirm?token={token}"
        bg.add_task(
            _send_reset_email,
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
        db: AsyncSession,
        user: models.User,
        token: str,
        request: Request,
    ) -> models.User:
        locale = resolve_locale(request=request, user=user)
        token_hash = _hash_token(token)
        now = datetime.now(UTC)

        result = await db.execute(
            select(models.EmailChangeToken).where(
                models.EmailChangeToken.token_hash == token_hash
            )
        )
        record = result.scalar_one_or_none()
        if record is None or record.user_id != user.id or record.used:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate(
                    "errors.users.email_confirmation_invalid", locale=locale
                ),
            )

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate(
                    "errors.users.email_confirmation_invalid", locale=locale
                ),
            )

        existing = await db.execute(
            select(models.User.id).where(
                func.lower(models.User.email) == record.new_email,
                models.User.id != user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            record.used = True
            await db.execute(
                update(models.EmailChangeToken)
                .where(
                    models.EmailChangeToken.user_id == user.id,
                    models.EmailChangeToken.id != record.id,
                )
                .values(used=True)
            )
            await db.commit()
            await attach_pending_email(db, user)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate(
                    "errors.users.email_confirmation_conflict", locale=locale
                ),
            )

        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
        db_user.email = record.new_email
        await db.execute(
            update(models.EmailChangeToken)
            .where(models.EmailChangeToken.id == record.id)
            .values(used=True)
        )
        await db.execute(
            update(models.EmailChangeToken)
            .where(
                models.EmailChangeToken.user_id == user.id,
                models.EmailChangeToken.id != record.id,
            )
            .values(used=True)
        )

        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)
        await attach_pending_email(db, db_user)
        if user is not db_user:
            await attach_pending_email(db, user)

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
        db: AsyncSession,
        user: models.User,
        payload: schemas.UserPasswordChangeIn,
        request: Request,
    ) -> tuple[bool, list[models.ActiveSession]]:
        locale = resolve_locale(request=request, user=user)
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.invalid_password", locale=locale),
            )
        if verify_password(payload.new_password, user.hashed_password):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=translate("errors.users.password_same", locale=locale),
            )
        try:
            hashed_password = get_password_hash(payload.new_password, locale=locale)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        db_user = await db.get(models.User, user.id, options=USER_MFA_LOAD_OPTIONS)
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
        revoked = await revoke_sessions_matching(db=db, whereclause=and_(*conditions))

        await db.commit()
        await db.refresh(db_user)
        await ensure_mfa_relationships_loaded(db, db_user)

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
