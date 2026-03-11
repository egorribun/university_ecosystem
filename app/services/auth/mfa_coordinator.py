from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

from fastapi import Request, Response, status

from app.auth import mfa
from app.auth import schemas as auth_schemas
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.models import ActiveSession, User
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.dtos import UserAuthDTO, UserDTO


class MfaCoordinator:
    def __init__(self, uow: UnitOfWork, auth_repo: AuthRepository):
        self.uow = uow
        self.repo = auth_repo

    async def check_and_issue_challenges(
        self,
        user: User | UserAuthDTO | UserDTO,
        request: Request,
        response: Response,
        locale: str,
    ) -> auth_schemas.PendingMfaResponse | None:
        if not user.mfa_required and not await self.repo.has_active_mfa(user.id):
            return None  # No MFA required

        capabilities = await self._resolve_mfa_capabilities(user)
        methods = await self._collect_mfa_challenges(user, locale, capabilities)

        if not methods:
            from app.api.validation import raise_http_error

            raise_http_error(
                status.HTTP_400_BAD_REQUEST, "errors.auth.mfa_totp_missing", locale
            )

        if response:
            response.status_code = status.HTTP_202_ACCEPTED

        await self.uow.commit()
        return auth_schemas.PendingMfaResponse(
            user_id=user.id,
            default_method=cast(
                "Literal['totp', 'webauthn'] | None",
                user.mfa_default_method or mfa.MFA_METHOD_TOTP,
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
