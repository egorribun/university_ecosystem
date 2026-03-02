from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import anyio
from fastapi import BackgroundTasks, Request, Response, status

# Removed circular dependency on app.api.deps
from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.auth.fingerprint import extract_fingerprint
from app.auth.security import verify_and_update_password
from app.core import metrics
from app.core.config import settings
from app.core.database import async_session
from app.core.localization import resolve_locale
from app.models.models import ActiveSession, User
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.schemas import schemas
from app.schemas.dtos import ActiveSessionDTO, UserAuthDTO, UserDTO
from app.tasks.email import send_lockout_alert

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from app.repositories.auth_repository import AuthRepository
    from app.repositories.user_repository import UserRepository
    from app.services.audit_service import AuditService
    from app.services.auth.lockout import LockoutService
    from app.services.session_service import SessionService
    from app.services.user.profile_service import UserProfileService

logger = logging.getLogger(__name__)


class LoginService:
    def __init__(
        self,
        auth_repo: AuthRepository,
        user_repo: UserRepository,
        profile_service: UserProfileService,
        session_service: SessionService,
        lockout_service: LockoutService,
        audit: AuditService,
        redis_session_service: Any,
        geolocation_service: Any,
    ):
        # P2-fix (audit 2026-02-26): AuthRepository is now injected via the DI
        # container (deps.py:get_login_service) instead of being constructed
        # inline here. This makes the dependency explicit, testable, and respects
        # the Dishka DI conventions used throughout the rest of the codebase.
        self.repo = auth_repo
        self.user_repo = user_repo
        self.profile_service = profile_service
        self.session_service = session_service
        self.lockout_service = lockout_service
        self.audit = audit
        self.redis_session = redis_session_service
        self.geolocation = geolocation_service

    async def perform_login(
        self,
        email: str,
        password: str,
        request: Request,
        response: Response,
        bg_tasks: BackgroundTasks,
        trust_device: bool = False,
    ) -> schemas.TokenWithProfile | auth_schemas.PendingMfaResponse:
        normalized_email = email.strip().lower()
        base_locale = resolve_locale(request=request)

        user = await self.profile_service.get_auth_user_by_email(normalized_email)
        locale = resolve_locale(request=request, user=user) if user else base_locale

        # 1. Check Lockout
        lock_until = await self.lockout_service.get_active_lockout(normalized_email)
        if lock_until:
            _detail, retry_after = self.lockout_service.get_lockout_message(
                locale, lock_until
            )
            self.audit.log(
                "auth.login.failure",
                request,
                level=logging.WARNING,
                user_id=user.id if user else None,
                reason="locked",
                extra={"lock_until": lock_until.isoformat()},
            )
            metrics.record_login_failure(reason="locked")
            # We raise here because it's a terminal state for this request
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

        # 2. Timing attack mitigation: constant-time or randomized delay
        import asyncio
        import secrets

        if not user:
            # Simulate Bcrypt/Argon2 load (randomized jitter 100-200ms)
            await asyncio.sleep(0.1 + (secrets.randbelow(100) / 1000.0))
            return cast(
                "schemas.TokenWithProfile | auth_schemas.PendingMfaResponse",
                await self._handle_invalid_user(
                    normalized_email, request, base_locale, bg_tasks
                ),
            )

        verified, new_hash = await verify_and_update_password(
            password, str(user.hashed_password)
        )

        if not verified:
            return cast(
                "schemas.TokenWithProfile | auth_schemas.PendingMfaResponse",
                await self._handle_invalid_password(
                    user, normalized_email, request, locale, bg_tasks
                ),
            )

        # 3. Valid credentials, check MFA
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

        if user.mfa_required or await self.repo.has_active_mfa(user.id):
            return await self._handle_mfa_required(user, request, response, locale)

        # 4. Success - Create Session
        return await self.finalize_login(user, request, response, bg_tasks)

    async def finalize_login(
        self,
        user: User | UserAuthDTO | UserDTO,
        request: Request,
        response: Response,
        bg_tasks: BackgroundTasks,
        mfa_completed: bool = False,
        method: str = "password",
    ) -> schemas.TokenWithProfile:
        client_ip, user_agent = self._extract_client_info(request)
        fingerprint = extract_fingerprint(request)

        metadata: dict[str, Any] = {
            "ip_address": client_ip,
            "user_agent": user_agent,
            "accept_language": fingerprint.accept_language,
            "fingerprint_hash": fingerprint.fingerprint_hash,
            "mfa_method": method if mfa_completed else None,
        }
        if mfa_completed:
            now_val = datetime.now(UTC)
            metadata["mfa_completed_at"] = now_val
            metadata["mfa_verified_at"] = now_val
            if hasattr(user, "model_copy"):
                # Handle Pydantic DTO
                user = user.model_copy(update={"mfa_last_verified_at": now_val})
            else:
                user.mfa_last_verified_at = now_val

        token, session = await self.session_service.create_access_token(
            sub=user.id,
            metadata=metadata,
            bg_tasks=bg_tasks,
        )

        self._set_access_token_cookie(response, token)

        # Rotate the CSRF token on every successful auth event (login, MFA step-up).
        # A CSRF token that was valid before authentication must not remain valid
        # after privilege escalation. (RZ-5: audit 2026-02-24)
        from app.core.csrf import signal_csrf_rotation

        signal_csrf_rotation(request)

        bg_tasks.add_task(
            self.record_login_history_bg,
            user.id,
            client_ip,
            user_agent,
            "success",
        )

        from app.auth.fingerprint import SessionFingerprint

        fp = SessionFingerprint(
            user_agent=user_agent or "",
            ip_address=client_ip or "",
            accept_language=metadata["accept_language"] or "",
            fingerprint_hash=metadata["fingerprint_hash"] or "",
        )
        # Fire and forget Redis write
        # (or await if critical, here await is fine as it's fast)
        await self.redis_session.create_session(
            jti=str(session.jti),
            user_id=user.id,
            fingerprint=fp,
            mfa_verified_at=session.mfa_verified_at,
        )

        self.audit.log(
            "auth.login.success",
            request,
            user_id=user.id,
            reason="authenticated",
        )
        metrics.record_login_success(method=method)

        return await self.build_token_response(
            user, token, session, include_token=False
        )

    async def build_token_response(
        self,
        user: User | UserAuthDTO | UserDTO,
        token: str,
        session: ActiveSession | ActiveSessionDTO | None,
        include_token: bool = True,
    ) -> schemas.TokenWithProfile:
        # Ensure that MFA relationships are loaded before validation
        if not isinstance(user, User):
            # If it's a DTO, we might need a real User object or the loader needs to handle DTOs
            # For now, let's assume it's a User or handle it
            pass

        # Cast needed because ensure_mfa_relationships_loaded return type includes None
        # but we know it won't be None as input is not None.
        user = cast(Any, await ensure_mfa_relationships_loaded(self.repo.db, user))

        # RED-ZONE: Ensure pending email is attached to UserOut if exists
        from app.services.auth_service import attach_pending_email

        temp_user = await attach_pending_email(self.repo.db, user)
        if temp_user is not None:
            user = temp_user

        from app.schemas.schemas import SessionSigningKeyOut, UserOut

        session_payload: SessionSigningKeyOut | None = None
        signing_key = getattr(session, "signing_key", None) if session else None
        if isinstance(signing_key, str) and signing_key:
            session_payload = SessionSigningKeyOut(signing_key=signing_key)

        return schemas.TokenWithProfile(
            access_token=token if include_token else None,
            user=UserOut.model_validate(user),
            session=session_payload,
        )

    async def _handle_invalid_user(
        self,
        email: str,
        request: Request,
        locale: str,
        bg_tasks: BackgroundTasks,
    ) -> Any:
        (
            lock_until,
            triggered,
            attempts,
        ) = await self.lockout_service.register_failed_attempt(email, None)
        self.audit.log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            reason="invalid_credentials",
        )
        if triggered and lock_until:
            duration_text = self.lockout_service.format_duration(
                locale, int((lock_until - datetime.now(UTC)).total_seconds())
            )
            _detail, retry_after = self.lockout_service.get_lockout_message(
                locale, lock_until
            )
            self.audit.log(
                "auth.login.locked",
                request,
                level=logging.WARNING,
                reason="lockout",
                until=lock_until.isoformat(),
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
        client_ip, user_agent = self._extract_client_info(request)
        bg_tasks.add_task(
            self.record_login_history_bg, None, client_ip, user_agent, "failure"
        )

        from app.api.validation import raise_unauthorized

        raise_unauthorized(
            locale,
            "errors.auth.credentials_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def _handle_invalid_password(
        self,
        user: User | UserAuthDTO | UserDTO,
        email: str,
        request: Request,
        locale: str,
        bg_tasks: BackgroundTasks,
    ) -> Any:
        (
            lock_until,
            triggered,
            attempts,
        ) = await self.lockout_service.register_failed_attempt(email, user.id)
        self.audit.log(
            "auth.login.failure",
            request,
            level=logging.WARNING,
            user_id=user.id,
            reason="invalid_credentials",
        )
        if triggered and lock_until:
            duration_text = self.lockout_service.format_duration(
                locale, int((lock_until - datetime.now(UTC)).total_seconds())
            )
            _detail, retry_after = self.lockout_service.get_lockout_message(
                locale, lock_until
            )
            self.audit.log(
                "auth.login.locked",
                request,
                level=logging.WARNING,
                user_id=user.id,
                reason="lockout",
                until=lock_until.isoformat(),
            )
            await self._trigger_lockout_alert(
                email, user.full_name or "", lock_until, attempts, locale
            )
            from app.api.validation import raise_http_error

            raise_http_error(
                status.HTTP_423_LOCKED,
                "errors.auth.account_locked",
                locale,
                headers={"Retry-After": str(retry_after)},
                duration=duration_text,
            )

        metrics.record_login_failure(reason="invalid_credentials")
        client_ip, user_agent = self._extract_client_info(request)
        bg_tasks.add_task(
            self.record_login_history_bg, user.id, client_ip, user_agent, "failure"
        )

        from app.api.validation import raise_unauthorized

        raise_unauthorized(
            locale,
            "errors.auth.credentials_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def _handle_mfa_required(
        self,
        user: User | UserAuthDTO | UserDTO,
        request: Request,
        response: Response,
        locale: str,
    ) -> auth_schemas.PendingMfaResponse:
        capabilities = await self._resolve_mfa_capabilities(user)
        methods = await self._collect_mfa_challenges(user, locale, capabilities)

        if not methods:
            # User has MFA enabled but no factors enrolled
            from app.api.validation import raise_http_error

            raise_http_error(
                status.HTTP_400_BAD_REQUEST,
                "errors.auth.mfa_totp_missing",
                locale,
            )

        if response:
            response.status_code = status.HTTP_202_ACCEPTED

        await self.repo.commit()
        return auth_schemas.PendingMfaResponse(
            user_id=user.id,
            default_method=user.mfa_default_method or mfa.MFA_METHOD_TOTP,
            methods=methods,
        )

    async def _resolve_mfa_capabilities(
        self, user: User | UserAuthDTO | UserDTO
    ) -> dict[str, bool]:
        """Helper to resolve MFA capabilities for a user."""
        return await self.repo.get_user_mfa_capabilities(user.id)

    async def _trigger_lockout_alert(
        self,
        email: str,
        full_name: str,
        lock_until: datetime,
        attempts: int,
        locale: str,
    ) -> None:
        await send_lockout_alert.kick(email, full_name, locale)  # type: ignore[attr-defined]
        # We don't log to audit again here as it's already logged in the caller
        # but we could add more metadata if needed.

    async def _collect_mfa_challenges(
        self,
        user: User | UserAuthDTO | UserDTO,
        locale: str,
        capabilities: Mapping[str, bool],
        session: ActiveSession | None = None,
    ) -> list[auth_schemas.MfaMethodChallengeOut]:
        methods: list[auth_schemas.MfaMethodChallengeOut] = []

        if capabilities.get(mfa.MFA_METHOD_TOTP):
            challenge = await mfa.start_totp_verification(
                self.repo.db, user=user, session=session, locale=locale
            )
            attempt_count, attempt_limit, remaining_attempts = (
                mfa.describe_challenge_attempts(
                    challenge, default_limit=settings.mfa_totp_attempt_limit
                )
            )
            methods.append(
                auth_schemas.MfaMethodChallengeOut(
                    method=mfa.MFA_METHOD_TOTP,
                    challenge_token=challenge.token,
                    challenge_expires_at=challenge.expires_at,
                    attempt_count=attempt_count,
                    attempt_limit=attempt_limit,
                    remaining_attempts=remaining_attempts,
                )
            )

        if capabilities.get(mfa.MFA_METHOD_WEBAUTHN):
            from app.services.webauthn import WebAuthnService

            service = WebAuthnService(self.repo.db)
            webauthn_options = await service.get_authentication_options(user)

            challenge = await mfa.issue_challenge(
                self.repo.db,
                user_id=user.id,
                session_id=session.id if session else None,
                challenge_type=mfa.CHALLENGE_TYPE_WEBAUTHN_AUTH,
                locale=locale,
                payload={"options": webauthn_options},
            )

            attempt_count, attempt_limit, remaining_attempts = (
                mfa.describe_challenge_attempts(
                    challenge, default_limit=settings.mfa_challenge_max_attempts
                )
            )

            methods.append(
                auth_schemas.MfaMethodChallengeOut(
                    method=mfa.MFA_METHOD_WEBAUTHN,
                    challenge_token=challenge.token,
                    challenge_expires_at=challenge.expires_at,
                    options=webauthn_options,
                    attempt_count=attempt_count,
                    attempt_limit=attempt_limit,
                    remaining_attempts=remaining_attempts,
                )
            )

        return methods

    def _extract_client_info(self, request: Request) -> tuple[str | None, str | None]:
        """Extract real client IP and user-agent from the request.

        Uses the centralised ``resolve_client_ip`` helper which respects the
        configured ``TRUSTED_PROXIES`` list.  This prevents X-Forwarded-For
        spoofing: an attacker prepending an arbitrary IP to the header is
        ignored unless the actual connecting IP is a trusted proxy.
        """
        from app.core.rate_limit import resolve_client_ip

        client_ip: str | None = resolve_client_ip(request) or None
        user_agent = request.headers.get("user-agent")
        return client_ip, user_agent

    def _set_access_token_cookie(self, response: Response, token: str) -> None:
        try:
            minutes = int(settings.access_token_expire_minutes)
        except (TypeError, ValueError):
            minutes = 60
        max_age = minutes * 60
        expires = datetime.now(UTC) + timedelta(minutes=minutes)

        response.set_cookie(
            "access_token_v2",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,  # type: ignore[arg-type]
            max_age=max_age,
            expires=expires,
            path="/",
        )

    @staticmethod
    def clear_access_token_cookie(response: Response) -> None:
        response.delete_cookie(
            "access_token_v2",
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        )

    async def record_login_history_bg(
        self,
        user_id: UUID | None,
        client_ip: str | None,
        user_agent: str | None,
        status_value: str,
        is_suspicious: bool = False,
    ) -> None:
        async with async_session() as db:
            from app.repositories.auth_repository import AuthRepository

            # Geolocation resolution is synchronous and IO-bound, run in thread
            location = await anyio.to_thread.run_sync(
                self.geolocation.resolve, client_ip or ""
            )

            # Use repo for record creation
            repo = AuthRepository(db)
            await repo.record_login_history(
                user_id=user_id,
                ip_address=client_ip or "unknown",
                user_agent=user_agent[:512] if user_agent else None,
                country=location.country,
                city=location.city,
                latitude=location.latitude,
                longitude=location.longitude,
                status=status_value,
                is_suspicious=is_suspicious,
            )
            await db.commit()
