import contextlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from fastapi import BackgroundTasks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.redis_session import get_session_backend
from app.core.config import settings
from app.repositories.active_session_repository import ActiveSessionRepository
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
    def __init__(self, db: AsyncSession, repo: ActiveSessionRepository):
        self.db = db
        self.repo = repo

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

        # 1. Serialization (Concurrency Control)
        # We attempt a Redis-based distributed lock first for scalability.
        lock_acquired = False
        redis_lock = None
        if settings.session_storage_backend == "redis":
            from app.deps.cache import RedisCache, get_cache

            cache = get_cache()
            if isinstance(cache, RedisCache):
                client = await cache._get_client()
                lock_key = f"lock:session_creation:{user_id}"
                redis_lock = client.lock(lock_key, timeout=10)
                try:
                    # Attempt to acquire lock for up to 2 seconds
                    lock_acquired = await redis_lock.acquire(blocking_timeout=2)
                except Exception:
                    logger.warning(
                        "Redis lock acquisition failed",
                        exc_info=True,
                        extra={
                            "user_id": str(user_id),
                            "lock_type": "session_creation",
                        },
                    )

        # Fallback to Postgres Advisory Lock if Redis is unavailable or fails
        if not lock_acquired and self.db.bind.dialect.name == "postgresql":
            # pg_advisory_xact_lock(int, int) requires 32-bit integers
            uid_int = int(user_id.int) % (2**31 - 1)
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(1, :uid)"), {"uid": uid_int}
            )

        try:
            # 2. Build and persist session record
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
                fields = ["ip_address", "user_agent", "accept_language", "fingerprint_hash", "mfa_method"]
                for key in fields:
                    if val := metadata.get(key):
                        session_data[key] = str(val)

                session_data["mfa_required"] = bool(metadata.get("mfa_required", False))
                if val := metadata.get("mfa_completed_at"):
                    session_data["mfa_completed_at"] = val
                if val := metadata.get("mfa_verified_at"):
                    session_data["mfa_verified_at"] = val

            session = await self.repo.create(session_data)

            # 3. Enforce concurrent session limit
            await self._enforce_concurrent_limit(user_id, jti, now)

            await self.repo.commit()
        finally:
            if lock_acquired and redis_lock:
                with contextlib.suppress(Exception):
                    await redis_lock.release()

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
        except (TypeError, ValueError):
            raise ValueError(
                "Subject (sub) must be a valid UUID for session persistence"
            )


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
        self, user_id: UUID, jti: str, iat: datetime, exp: datetime, extra: dict | None
    ) -> str:
        payload = {
            "sub": str(user_id),
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
        bg_tasks: BackgroundTasks | None,
    ) -> None:
        # We reuse the existing background task helper if available, or call directly
        # For better SRP, this could be moved here too.
        args = (user_id, jti, expires_at, session.ip_address, session.user_agent)
        if bg_tasks:
            bg_tasks.add_task(register_session_bg, *args)
        else:
            await register_session_bg(*args)
