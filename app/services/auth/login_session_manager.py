from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from fastapi import BackgroundTasks, Request, Response

from app.auth.fingerprint import SessionFingerprint, extract_fingerprint
from app.core import metrics
from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.models import User
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.schemas import schemas

if TYPE_CHECKING:
    from uuid import UUID

    from app.models import ActiveSession
    from app.schemas.dtos import ActiveSessionDTO, UserAuthDTO, UserDTO
    from app.services.audit_service import AuditService
    from app.services.session_service import SessionService

logger = get_logger(__name__)


class LoginSessionManager:
    def __init__(
        self,
        session_service: SessionService,
        redis_session_service: Any,
        geolocation_service: Any,
        audit: AuditService,
    ):
        self.session_service = session_service
        self.redis_session = redis_session_service
        self.geolocation = geolocation_service
        self.audit = audit

    async def finalize_login(
        self,
        user: User | UserAuthDTO | UserDTO,
        request: Request,
        response: Response,
        bg_tasks: BackgroundTasks,
        db_session: Any,
        mfa_completed: bool = False,
        method: str = "password",
    ) -> schemas.TokenWithProfile:
        client_ip, user_agent = self.extract_client_info(request)
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
                user = user.model_copy(update={"mfa_last_verified_at": now_val})
            else:
                user.mfa_last_verified_at = now_val

        # W136 SW1: embed `is_active` claim in JWT so gateway's `claims.IsActive`
        # check at services/gateway/middleware/auth.go:720 can enforce user
        # status edge-side (defense-in-depth alongside session revocation set).
        # Closes W135 §Honesty #2 — pre-W136 the gateway returned 403 for ALL
        # authed requests because the claim was missing from the payload.
        #
        # W166 SW1: embed `role` claim alongside `is_active` so SSR-side
        # `_admin.tsx:34` beforeLoad reads role directly from JWT payload
        # (via `ssrAuth.ts:127` validateJwt extraction) instead of waiting
        # for the async `/users/me` call to settle. Closes W165 NEW W166+
        # candidate #1 (admin auth JWT-no-role-claim race on cold-cache
        # direct /admin/* URL navigation).
        token, session = await self.session_service.create_access_token(
            sub=user.id,
            metadata=metadata,
            bg_tasks=bg_tasks,
            extra_claims={
                "is_active": bool(user.is_active),
                "role": user.role.value,
            },
        )

        self._set_access_token_cookie(response, token)

        from app.core.csrf import signal_csrf_rotation

        signal_csrf_rotation(request)

        bg_tasks.add_task(
            self.record_login_history_bg,
            user.id,
            client_ip,
            user_agent,
            "success",
        )

        fp = SessionFingerprint(
            user_agent=user_agent or "",
            ip_address=client_ip or "",
            accept_language=metadata["accept_language"] or "",
            fingerprint_hash=metadata["fingerprint_hash"] or "",
        )
        await self.redis_session.create_session(
            jti=str(session.jti),
            user_id=user.id,
            fingerprint=fp,
            mfa_verified_at=session.mfa_verified_at,
        )

        self.audit.log(
            "auth.login.success", request, user_id=user.id, reason="authenticated"
        )
        metrics.record_login_success(method=method)

        return await self.build_token_response(
            user, token, session, db_session, include_token=False
        )

    async def build_token_response(
        self,
        user: User | UserAuthDTO | UserDTO,
        token: str,
        session: ActiveSession | ActiveSessionDTO | None,
        db_session: Any,
        include_token: bool = True,
    ) -> schemas.TokenWithProfile:
        user = cast(Any, await ensure_mfa_relationships_loaded(db_session, user))

        from app.services.auth_service import attach_pending_email

        temp_user = await attach_pending_email(db_session, user)
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

    def extract_client_info(self, request: Request) -> tuple[str | None, str | None]:
        from app.core.ratelimit import resolve_client_ip

        client_ip: str | None = resolve_client_ip(request) or None
        user_agent = request.headers.get("user-agent")
        return client_ip, user_agent

    def _set_access_token_cookie(self, response: Response, token: str) -> None:
        try:
            raw_minutes = settings.security.access_token_expire_minutes
            minutes = int(raw_minutes)
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

    async def record_login_history_bg(
        self,
        user_id: UUID | None,
        client_ip: str | None,
        user_agent: str | None,
        status_value: str,
        is_suspicious: bool = False,
    ) -> None:
        async with async_session() as db:
            import asyncio

            from app.repositories.auth_repository import AuthRepository

            location = await asyncio.to_thread(
                self.geolocation.resolve, client_ip or ""
            )

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
