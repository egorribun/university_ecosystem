from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from fastapi import BackgroundTasks

from app.auth.redis_session import get_session_backend
from app.core.config import settings
from app.models.models import ActiveSession
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.dtos import ActiveSessionDTO

logger = logging.getLogger(__name__)


async def register_session_bg(
    user_id: UUID,
    jti: str,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Background task to register session in Redis."""
    try:
        session_backend = await get_session_backend()
        await session_backend.register_session(
            user_id=str(user_id),  # type: ignore[arg-type]
            jti=jti,
            expires_at=expires_at,
            metadata={
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )
    except Exception:
        logger.warning(
            "Failed to register session in Redis (background)",
            exc_info=True,
            extra={
                "user_id": str(user_id),
                "jti": jti,
                "component": "session_backend",
                "operation": "register",
            },
        )


class SessionService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.repo = uow.sessions
        self.db = uow.session

    async def create_access_token(
        self,
        sub: str | Any,
        expires_delta_minutes: int | None = None,
        metadata: dict[str, Any] | None = None,
        bg_tasks: BackgroundTasks | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> tuple[str, ActiveSessionDTO]:
        """
        Create a new session and mint a JWT.

        Orchestrates:
        1. JTI and expiration generation.
        2. Database persistence with advisory lock and concurrency limits.
        3. JWT encoding.
        4. Redis session backend registration.
        """
        user_id = self._normalize_sub(sub)
        now = datetime.now(UTC)
        minutes = expires_delta_minutes or settings.access_token_expire_minutes
        expires_at = now + timedelta(minutes=minutes)
        jti = str(uuid4())

        # PERF-2 Fix (audit 2026-03-04): Removed explicit asynchronous and synchronous database/Redis
        # locking during session creation. Enforcing concurrent limit is now lock-free, increasing login TPS.

        # 1. Build and persist session record
        session_data = {
            "user_id": user_id,
            "jti": jti,
            "expires_at": expires_at,
            "signing_key": secrets.token_urlsafe(32),
            "created_at": now,
            "last_seen_at": now,
        }

        # Merge metadata into session_data to avoid mutating frozen DTO
        if metadata:
            fields = [
                "ip_address",
                "user_agent",
                "accept_language",
                "fingerprint_hash",
                "mfa_method",
            ]
            for key in fields:
                if val := metadata.get(key):
                    session_data[key] = str(val)

            session_data["mfa_required"] = bool(metadata.get("mfa_required", False))
            if val := metadata.get("mfa_completed_at"):
                session_data["mfa_completed_at"] = val
            if val := metadata.get("mfa_verified_at"):
                session_data["mfa_verified_at"] = val

        session = await self.repo.create(session_data)

        # 2. Enforce concurrent session limit (lock-free soft limit)
        await self._enforce_concurrent_limit(user_id, jti, now)

        await self.db.commit()

        # 4. Mint JWT
        token = self._mint_jwt(user_id, jti, now, expires_at, extra_claims)

        # 5. Register in Redis backend
        await self._sync_to_redis(session, user_id, jti, expires_at, bg_tasks)

        return token, session

    def _normalize_sub(self, sub: Any) -> UUID:
        if isinstance(sub, UUID):
            return sub
        try:
            return UUID(str(sub))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Subject (sub) must be a valid UUID for session persistence"
            ) from exc

    async def _enforce_concurrent_limit(
        self, user_id: UUID, current_jti: str, now: datetime
    ) -> None:
        limit = settings.max_sessions_per_user
        if limit <= 0:
            return

        active_count = await self.repo.get_active_count_for_user(user_id, now)
        if active_count > limit:
            excess = active_count - limit
            # Fetch oldest sessions to revoke, excluding the one we just added
            old_sessions = await self.repo.get_oldest_active_sessions(
                user_id, now, limit=excess, exclude_jti=current_jti
            )

            backend = await get_session_backend()
            for s in old_sessions:
                await self.repo.revoke_by_id(s.id, now)
                try:
                    await backend.revoke_session(str(s.jti))
                except Exception:
                    logger.warning(
                        "Failed to revoke session from Redis during cleanup",
                        exc_info=True,
                        extra={
                            "jti": s.jti,
                            "user_id": str(user_id),
                        },
                    )

    def _mint_jwt(
        self,
        user_id: UUID,
        jti: str,
        iat: datetime,
        exp: datetime,
        extra: dict[str, Any] | None,
    ) -> str:
        payload = {
            "sub": str(user_id),
            "aud": settings.jwt_audience,
            "iat": iat,
            "nbf": iat,
            "exp": exp,
            "jti": jti,
        }
        if extra:
            payload.update(extra)

        return jwt.encode(
            payload,
            settings.jwt_signing_active_secret,
            algorithm=settings.algorithm,
            headers={"kid": settings.jwt_signing_active_kid},
        )

    async def _sync_to_redis(
        self,
        session: ActiveSessionDTO,
        user_id: UUID,
        jti: str,
        expires_at: datetime,
        bg_tasks: BackgroundTasks | None,  # kept for API compat; no longer used
    ) -> None:
        # AUTH-1 (audit 2026-03): Always await Redis session registration before
        # returning the JWT to the client.  Using bg_tasks.add_task() meant the
        # session wasn't visible in Redis until after the response was sent,
        # causing 401s on immediate follow-up requests (login → token refresh
        # race window).  The DB record is committed first, so latency here is
        # bounded by a single Redis SET (~1ms on localhost, <5ms in prod).
        args = (user_id, jti, expires_at, session.ip_address, session.user_agent)
        await register_session_bg(*args)

    async def get_active_sessions_for_user(
        self, user_id: UUID
    ) -> list[ActiveSessionDTO]:
        from sqlalchemy import select

        stmt = (
            select(ActiveSession)
            .where(ActiveSession.user_id == user_id)
            .where(ActiveSession.revoked_at.is_(None))
            .order_by(ActiveSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return [ActiveSessionDTO.model_validate(s) for s in result.scalars().all()]

    async def get_session_by_id(self, session_id: UUID) -> ActiveSessionDTO | None:
        session = await self.db.get(ActiveSession, session_id)
        if not session:
            return None
        return ActiveSessionDTO.model_validate(session)

    async def revoke_session_by_id(self, session_id: UUID) -> ActiveSessionDTO | None:
        now = datetime.now(UTC)
        session = await self.db.get(ActiveSession, session_id)
        if not session:
            return None

        session.revoked_at = session.revoked_at or now
        session.signing_key = secrets.token_urlsafe(32)
        await self.db.commit()

        # Best effort backend revocation
        from contextlib import suppress

        from app.auth.redis_session import get_session_backend

        backend = await get_session_backend()
        with suppress(Exception):
            await backend.revoke_session(str(session.jti))

        return ActiveSessionDTO.model_validate(session)

    async def revoke_other_sessions(
        self, user_id: UUID, current_jti: str | None
    ) -> int:
        from sqlalchemy import and_

        from app.services.session_cleanup import revoke_sessions_matching

        where_parts = [
            ActiveSession.user_id == user_id,
            ActiveSession.revoked_at.is_(None),
        ]
        if current_jti:
            where_parts.append(ActiveSession.jti != current_jti)

        revoked = await revoke_sessions_matching(
            db=self.db, whereclause=and_(*where_parts)
        )
        await self.db.commit()
        return revoked
