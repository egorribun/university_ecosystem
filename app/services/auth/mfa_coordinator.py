from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

from fastapi import Request, Response, status

from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.core.config import settings

if TYPE_CHECKING:
    from app.auth.mfa.email_otp import EmailOtpService
    from app.models import ActiveSession, User
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.dtos import UserAuthDTO, UserDTO


class MfaCoordinator:
    PREAUTH_COOKIE_NAME = "mfa_pre_auth_v1"

    def __init__(
        self,
        uow: UnitOfWork,
        auth_repo: AuthRepository,
        email_otp_service: EmailOtpService | None = None,
    ):
        self.uow = uow
        self.repo = auth_repo
        self.email_otp_service = email_otp_service

    def get_email_otp_service(self) -> EmailOtpService:
        """Construct the key-backed service only when an email factor is used."""
        if self.email_otp_service is None:
            from app.auth.mfa.email_otp import (
                RuntimeMfaRateLimiter,
                build_configured_email_otp_service,
            )

            self.email_otp_service = build_configured_email_otp_service(
                rate_limiter=RuntimeMfaRateLimiter()
            )
        return self.email_otp_service

    async def check_and_issue_challenges(
        self,
        user: User | UserAuthDTO | UserDTO,
        request: Request,
        response: Response,
        locale: str,
        trust_device: bool = False,
    ) -> auth_schemas.PendingMfaResponse | None:
        if not user.mfa_required and not await self.repo.has_active_mfa(user.id):
            return None  # No MFA required

        trusted_token = request.cookies.get(settings.trusted_device_cookie_name)
        if trusted_token:
            from app.core.ratelimit import resolve_client_ip

            rotated_token = await mfa.verify_and_rotate_trusted_device_token(
                self.repo.db,
                user=cast("User", user),
                token=trusted_token,
                request_ip=resolve_client_ip(request) or None,
                request_ua=request.headers.get("user-agent"),
            )
            if rotated_token:
                response.set_cookie(
                    settings.trusted_device_cookie_name,
                    rotated_token,
                    httponly=True,
                    secure=settings.cookie_secure,
                    samesite=settings.cookie_samesite,  # type: ignore[arg-type]
                    max_age=settings.trusted_device_expire_days * 86400,
                    path="/",
                )
                return None

        capabilities = await self._resolve_mfa_capabilities(user)
        preferred = str(user.mfa_default_method or "")
        default_method = (
            preferred
            if preferred in {mfa.MFA_METHOD_TOTP, mfa.MFA_METHOD_EMAIL_OTP}
            and capabilities.get(preferred, False)
            else (
                mfa.MFA_METHOD_TOTP
                if capabilities.get(mfa.MFA_METHOD_TOTP, False)
                else mfa.MFA_METHOD_EMAIL_OTP
            )
        )
        preauth_identifier = secrets.token_urlsafe(24)
        methods = await self._collect_mfa_challenges(
            user,
            locale,
            capabilities,
            request=request,
            flow="login",
            trust_device=trust_device,
            session_identifier=preauth_identifier,
        )

        if not methods:
            from app.api.validation import raise_http_error

            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.auth.mfa_totp_missing", locale
            )

        if response:
            response.status_code = status.HTTP_202_ACCEPTED
            response.set_cookie(
                self.PREAUTH_COOKIE_NAME,
                preauth_identifier,
                httponly=True,
                secure=settings.cookie_secure,
                samesite=settings.cookie_samesite,  # type: ignore[arg-type]
                max_age=settings.mfa_challenge_ttl_seconds,
                path="/",
            )

        return auth_schemas.PendingMfaResponse(
            user_id=user.id,
            default_method=cast(
                "Literal['totp', 'email_otp'] | None",
                default_method,
            ),
            methods=methods,
        )

    async def _resolve_mfa_capabilities(
        self, user: User | UserAuthDTO | UserDTO
    ) -> dict[str, bool]:
        return await self.repo.get_user_mfa_capabilities(user.id)

    async def _collect_mfa_challenges(
        self,
        user: User | UserAuthDTO | UserDTO,
        locale: str,
        capabilities: Mapping[str, bool],
        session: ActiveSession | None = None,
        request: Request | None = None,
        flow: Literal["login", "step_up"] = "login",
        trust_device: bool = False,
        session_identifier: str | None = None,
    ) -> list[auth_schemas.MfaMethodChallengeOut]:
        methods: list[auth_schemas.MfaMethodChallengeOut] = []
        from app.core.fingerprint import extract_request_fingerprint
        from app.core.ratelimit import resolve_client_ip

        fingerprint = extract_request_fingerprint(request) if request else "0" * 64
        client_ip = resolve_client_ip(request) if request else "unknown"
        bound_session_identifier = session_identifier or (
            str(session.id) if session else secrets.token_urlsafe(24)
        )

        if capabilities.get(mfa.MFA_METHOD_TOTP):
            challenge = await mfa.start_totp_verification(
                self.repo.db,
                user=user,
                session=session,
                locale=locale,
                payload={"trust_device": trust_device},
                flow=flow,
                session_identifier=bound_session_identifier,
                client_fingerprint=fingerprint,
            )
            attempt_count, attempt_limit, remaining_attempts = (
                mfa.describe_challenge_attempts(
                    challenge.challenge,
                    default_limit=settings.mfa_totp_attempt_limit,
                )
            )
            methods.append(
                auth_schemas.MfaMethodChallengeOut(
                    method=mfa.MFA_METHOD_TOTP,
                    challenge_token=challenge.challenge_token,
                    challenge_expires_at=challenge.expires_at,
                    attempt_count=attempt_count,
                    attempt_limit=attempt_limit,
                    remaining_attempts=remaining_attempts,
                    revision=challenge.challenge.revision,
                )
            )

        if capabilities.get(mfa.MFA_METHOD_EMAIL_OTP):
            email_otp_service = self.get_email_otp_service()
            issued = await email_otp_service.issue(
                self.repo.db,
                user_id=user.id,
                flow=flow,
                session_identifier=bound_session_identifier,
                client_fingerprint=fingerprint,
                client_ip=client_ip or "unknown",
                locale=locale,
                trust_device=trust_device,
            )
            methods.append(
                auth_schemas.MfaMethodChallengeOut(
                    method=mfa.MFA_METHOD_EMAIL_OTP,
                    challenge_token=issued.challenge_token,
                    challenge_expires_at=issued.expires_at,
                    attempt_count=0,
                    attempt_limit=5,
                    remaining_attempts=5,
                    delivery_hint=issued.delivery_hint,
                    resend_available_at=issued.resend_available_at,
                    revision=issued.revision,
                )
            )

        return methods
