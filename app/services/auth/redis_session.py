from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

from redis.exceptions import RedisError

from app.auth.fingerprint import SessionFingerprint
from app.auth.revocation import get_revocation_redis_client, revoke_with_tombstone
from app.core.config import settings
from app.core.logging import get_logger
from app.core.ratelimit import get_shared_client as _get_shared_client

logger = get_logger(__name__)


class RedisSessionData(TypedDict):
    user_id: str
    # RZ-3: session_id cached alongside user_id so the auth hot-path (cache-hit)
    # can load ActiveSession via O(1) pk lookup instead of an extra WHERE-jti query.
    session_id: str | None
    fingerprint_hash: str | None
    mfa_verified_at: str | None  # ISO format
    last_seen_at: str | None  # ISO format
    created_at: str
    is_active: bool


class RedisSessionService:
    """
    Manages active session state in Redis for high-performance authentication.

    Key Schema: session:{jti} -> Hash
    """

    KEY_PREFIX = "session:v2:"

    def __init__(self, redis_url: str | None = None):
        # Session cache and revocation security state intentionally use
        # different Redis processes and memory policies.
        self.redis_url = redis_url or settings.cache_redis_url
        self.ttl_seconds = int(settings.access_token_expire_minutes) * 60

    async def create_session(
        self,
        jti: str,
        user_id: UUID,
        fingerprint: SessionFingerprint | None,
        mfa_verified_at: datetime | None,
        session_id: UUID | None = None,
    ) -> None:
        """Cache a newly created session in Redis."""
        if not self.redis_url:
            return

        key = f"{self.KEY_PREFIX}{jti}"
        now = datetime.now(UTC)

        data = {
            "user_id": str(user_id),
            # RZ-3: Store session_id so deps.py cache-hit path avoids a second
            # DB round-trip (WHERE jti = ...) on every authenticated request.
            "session_id": str(session_id) if session_id else "",
            "fingerprint_hash": fingerprint.fingerprint_hash if fingerprint else "",
            "mfa_verified_at": mfa_verified_at.isoformat() if mfa_verified_at else "",
            "last_seen_at": now.isoformat(),
            "created_at": now.isoformat(),
            "is_active": "1",
        }

        try:
            client = await cast("Awaitable[Any]", _get_shared_client(self.redis_url))
            # Use HSET (Redis 4.0+)
            await cast(
                "Awaitable[Any]", client.hset(key, mapping=cast("dict[Any, Any]", data))
            )
            await cast("Awaitable[Any]", client.expire(key, self.ttl_seconds))
        except (RedisError, OSError) as e:
            logger.warning(
                "Failed to cache session %s in Redis: %s", jti, e
            )  # LOW-W19: lazy logging

    async def get_session(self, jti: str) -> RedisSessionData | None:
        """Retrieve session data from Redis.

        Returns None on cache miss, Redis failure, or when the session has been
        marked inactive (is_active != "1"). Callers can treat None as a cache
        miss and fall back to the DB, which enforces revocation correctly.
        """
        if not self.redis_url:
            return None

        key = f"{self.KEY_PREFIX}{jti}"
        try:
            client = await cast("Awaitable[Any]", _get_shared_client(self.redis_url))
            raw = await cast("Awaitable[Any]", client.hgetall(key))
            if not raw:
                return None

            # Convert bytes to string if needed
            # (redis-py decode_responses=False default in rate_limit)
            # rate_limit pool uses decode_responses=False
            data = {
                k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8")
                if isinstance(v, bytes)
                else v
                for k, v in raw.items()
            }

            # If the session has been explicitly revoked (is_active="0"),
            # treat as cache miss so the caller falls through to the DB,
            # which will correctly enforce the revoked_at column.
            if data.get("is_active") != "1":
                return None

            return RedisSessionData(
                user_id=data.get("user_id", ""),
                session_id=data.get("session_id") or None,
                fingerprint_hash=data.get("fingerprint_hash") or None,
                mfa_verified_at=data.get("mfa_verified_at") or None,
                last_seen_at=data.get("last_seen_at") or None,
                created_at=data.get("created_at", ""),
                is_active=True,
            )
        except (RedisError, OSError):
            # Fail open (fallback to DB)
            return None

    async def update_last_seen(self, jti: str) -> None:
        """Update last_seen_at timestamp efficiently."""
        if not self.redis_url:
            return

        key = f"{self.KEY_PREFIX}{jti}"
        now_str = datetime.now(UTC).isoformat()
        try:
            client = await cast("Awaitable[Any]", _get_shared_client(self.redis_url))
            # Fire and forget update
            await cast("Awaitable[Any]", client.hset(key, "last_seen_at", now_str))
            # Refresh TTL
            await cast("Awaitable[Any]", client.expire(key, self.ttl_seconds))
        except (RedisError, OSError):
            pass

    async def revoke_session(
        self, jti: str, expires_at: datetime | None = None
    ) -> None:
        """Atomically write the gateway tombstone and remove cached state."""
        key = f"{self.KEY_PREFIX}{jti}"
        try:
            client = None
            if self.redis_url:
                client = await cast(
                    "Awaitable[Any]", _get_shared_client(self.redis_url)
                )
            revocation_client = await get_revocation_redis_client()
            await revoke_with_tombstone(
                client,
                session_key=key,
                jti=jti,
                expires_at=expires_at,
                revocation_redis_client=revocation_client,
            )
            try:
                await cast(
                    "Awaitable[Any]",
                    revocation_client.publish("session:revocations", jti),
                )
            except (RedisError, OSError):
                logger.warning("Failed to publish session revocation for jti=%s", jti)
        except (RedisError, OSError) as e:
            logger.error(
                "Failed to revoke session %s in Redis: %s — refusing to "
                "report a successful revocation",
                jti,
                e,
            )
            raise
