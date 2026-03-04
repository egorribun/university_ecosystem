from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import BackgroundTasks, Request, status

from app.auth.security import verify_and_update_password
from app.core import metrics

if TYPE_CHECKING:
    from app.repositories.user_repository import UserRepository
    from app.schemas.dtos import UserAuthDTO
    from app.services.audit_service import AuditService
    from app.services.auth.lockout import LockoutService
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.user.profile_service import UserProfileService

logger = logging.getLogger(__name__)

class CredentialValidator:
    def __init__(
        self,
        user_repo: UserRepository,
        profile_service: UserProfileService,
        lockout_service: LockoutService,
        audit: AuditService,
        session_manager: LoginSessionManager,
    ):
        self.user_repo = user_repo
        self.profile_service = profile_service
        self.lockout_service = lockout_service
        self.audit = audit
        self.session_manager = session_manager

    async def validate_credentials(
        self,
        email: str,
        password: str,
        request: Request,
        locale: str,
        bg_tasks: BackgroundTasks,
    ) -> UserAuthDTO:
        """
        Validates credentials and returns the User object.
        Raises HTTPException if validation fails or account is locked.
        """
        normalized_email = email.strip().lower()

        # locale from request ignores user preferences initially for lockout checks
        user = await self.profile_service.get_auth_user_by_email(normalized_email)

        # 1. Check Lockout
        lock_until = await self.lockout_service.get_active_lockout(normalized_email)
        if lock_until:
            _detail, retry_after = self.lockout_service.get_lockout_message(locale, lock_until)
            self.audit.log(
                "auth.login.failure",
                request,
                level=logging.WARNING,
                user_id=user.id if user else None,
                reason="locked",
                extra={"lock_until": lock_until.isoformat()},
            )
            metrics.record_login_failure(reason="locked")
            from app.api.validation import raise_http_error
            duration_text = self.lockout_service.format_duration(
                locale, int((lock_until - datetime.now(UTC)).total_seconds())
            )
            raise_http_error(
                status.HTTP_423_LOCKED,
                "errors.auth.account_locked",
                locale,
                headers={"Retry-After": str(retry_after)},
                duration=duration_text,
            )

        if not user:
            await asyncio.sleep(0.1 + (secrets.randbelow(100) / 1000.0))
            await self._handle_invalid_user(normalized_email, request, locale, bg_tasks)
            return cast("UserAuthDTO", None)

        verified, new_hash = await verify_and_update_password(
            password, str(user.hashed_password)
        )

        if not verified:
            from app.core.localization import resolve_locale
            user_locale = resolve_locale(request=request, user=user)
            await self._handle_invalid_password(user, normalized_email, request, user_locale, bg_tasks)
            return cast("UserAuthDTO", None)

        if new_hash:
            await self.user_repo.update(user.id, {"hashed_password": new_hash})
            await self.user_repo.commit()

        if await self.lockout_service.clear_failed_attempts(normalized_email) > 0:
            self.audit.log(
                "auth.login.unlocked",
                request,
                user_id=user.id,
                reason="successful_login",
            )

        return user

    async def _handle_invalid_user(
        self,
        email: str,
        request: Request,
        locale: str,
        bg_tasks: BackgroundTasks,
    ) -> None:
        (lock_until, triggered, attempts) = await self.lockout_service.register_failed_attempt(email, None)
        self.audit.log("auth.login.failure", request, level=logging.WARNING, reason="invalid_credentials")

        if triggered and lock_until:
            duration_text = self.lockout_service.format_duration(
                locale, int((lock_until - datetime.now(UTC)).total_seconds())
            )
            _detail, retry_after = self.lockout_service.get_lockout_message(locale, lock_until)
            self.audit.log(
                "auth.login.locked", request, level=logging.WARNING, reason="lockout", until=lock_until.isoformat()
            )
            await self._trigger_lockout_alert(email, "", lock_until, attempts, locale)
            from app.api.validation import raise_http_error
            raise_http_error(
                status.HTTP_423_LOCKED,
                "errors.auth.account_locked",
                locale,
                headers={"Retry-After": str(retry_after)},
                duration=duration_text,
            )

        metrics.record_login_failure(reason="invalid_credentials")
        client_ip, user_agent = self.session_manager.extract_client_info(request)
        bg_tasks.add_task(self.session_manager.record_login_history_bg, None, client_ip, user_agent, "failure")

        from app.api.validation import raise_unauthorized
        raise_unauthorized(locale, "errors.auth.credentials_invalid", headers={"WWW-Authenticate": "Bearer"})

    async def _handle_invalid_password(
        self,
        user: Any,
        email: str,
        request: Request,
        locale: str,
        bg_tasks: BackgroundTasks,
    ) -> None:
        (lock_until, triggered, attempts) = await self.lockout_service.register_failed_attempt(email, user.id)
        self.audit.log(
            "auth.login.failure", request, level=logging.WARNING, user_id=user.id, reason="invalid_credentials"
        )

        if triggered and lock_until:
            duration_text = self.lockout_service.format_duration(
                locale, int((lock_until - datetime.now(UTC)).total_seconds())
            )
            _detail, retry_after = self.lockout_service.get_lockout_message(locale, lock_until)
            self.audit.log(
                "auth.login.locked", request, level=logging.WARNING, user_id=user.id, reason="lockout", until=lock_until.isoformat()
            )
            await self._trigger_lockout_alert(email, user.full_name or "", lock_until, attempts, locale)
            from app.api.validation import raise_http_error
            raise_http_error(
                status.HTTP_423_LOCKED,
                "errors.auth.account_locked",
                locale,
                headers={"Retry-After": str(retry_after)},
                duration=duration_text,
            )

        metrics.record_login_failure(reason="invalid_credentials")
        client_ip, user_agent = self.session_manager.extract_client_info(request)
        bg_tasks.add_task(self.session_manager.record_login_history_bg, user.id, client_ip, user_agent, "failure")

        from app.api.validation import raise_unauthorized
        raise_unauthorized(locale, "errors.auth.credentials_invalid", headers={"WWW-Authenticate": "Bearer"})

    async def _trigger_lockout_alert(
        self, email: str, full_name: str, lock_until: datetime, attempts: int, locale: str
    ) -> None:
        from app.tasks.email import send_lockout_alert
        await send_lockout_alert.kick(email, full_name, locale)  # type: ignore[attr-defined]
