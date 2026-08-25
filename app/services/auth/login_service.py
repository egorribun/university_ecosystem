from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, Request, Response

from app.auth import schemas as auth_schemas
from app.core.localization import resolve_locale
from app.core.logging import get_logger
from app.schemas import schemas

if TYPE_CHECKING:
    from app.auth.mfa.email_otp import EmailOtpService
    from app.core.protocols import AsyncDatabaseSession
    from app.models import User
    from app.schemas.dtos import UserAuthDTO, UserDTO
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.mfa_coordinator import MfaCoordinator

logger = get_logger(__name__)


class LoginService:
    """Facade orchestrating CredentialValidator, MfaCoordinator, and LoginSessionManager."""

    def __init__(
        self,
        validator: CredentialValidator,
        mfa_coord: MfaCoordinator,
        session_manager: LoginSessionManager,
        db_session: AsyncDatabaseSession,
    ) -> None:
        self.validator = validator
        self.mfa_coord = mfa_coord
        self.session_manager = session_manager
        self.db = db_session

        # Expose the repository for narrow compatibility with direct callers.
        self.repo = self.mfa_coord.repo

    async def perform_login(
        self,
        email: str,
        password: str,
        request: Request,
        response: Response,
        bg_tasks: BackgroundTasks,
        trust_device: bool = False,
    ) -> schemas.TokenWithProfile | auth_schemas.PendingMfaResponse:
        locale = resolve_locale(request=request)

        # 1. Validate Credentials and rate-limits
        user = await self.validator.validate_credentials(
            email=email,
            password=password,
            request=request,
            locale=locale,
            bg_tasks=bg_tasks,
        )

        user_locale = resolve_locale(request=request, user=user)

        # 2. Check MFA requirements
        mfa_response = await self.mfa_coord.check_and_issue_challenges(
            user=user,
            request=request,
            response=response,
            locale=user_locale,
            trust_device=trust_device,
        )
        if mfa_response:
            return mfa_response

        # 3. Create Session
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
        return await self.session_manager.finalize_login(
            user=user,
            request=request,
            response=response,
            bg_tasks=bg_tasks,
            db_session=self.db,
            mfa_completed=mfa_completed,
            method=method,
        )

    @staticmethod
    def clear_access_token_cookie(response: Response) -> None:
        from app.core.config import settings

        response.delete_cookie(
            "access_token_v2",
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        )

    async def _resolve_mfa_capabilities(
        self, user: User | UserAuthDTO | UserDTO
    ) -> dict[str, bool]:
        """Delegate capabilities resolution to MfaCoordinator."""
        return await self.mfa_coord._resolve_mfa_capabilities(user)

    async def _collect_mfa_challenges(
        self,
        user: User | UserAuthDTO | UserDTO,
        locale: str,
        capabilities: dict[str, bool],
        session: Any | None = None,
        request: Request | None = None,
        flow: str = "login",
    ) -> list[auth_schemas.MfaMethodChallengeOut]:
        """Delegate challenges collection to MfaCoordinator."""
        return await self.mfa_coord._collect_mfa_challenges(
            user,
            locale,
            capabilities,
            session,
            request=request,
            flow=flow,  # type: ignore[arg-type]
        )

    def get_email_otp_service(self) -> EmailOtpService:
        """Resolve the email OTP service lazily for email-only endpoints."""
        return self.mfa_coord.get_email_otp_service()

    async def complete_step_up(
        self,
        *,
        user: User,
        session: Any,
        request: Request,
        method: str,
    ) -> schemas.TokenWithProfile:
        return await self.session_manager.complete_step_up(
            user=user,
            session=session,
            request=request,
            db_session=self.db,
            method=method,
        )

    async def publish_completed_step_up(
        self,
        *,
        user: User,
        session: Any,
        request: Request,
    ) -> None:
        await self.session_manager.publish_completed_step_up(
            user=user,
            session=session,
            request=request,
        )
