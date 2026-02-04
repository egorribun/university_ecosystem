import logging
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from redis.exceptions import RedisError

from app.auth.fingerprint import SessionFingerprint
from app.core.config import settings
from app.core.rate_limit import _get_shared_client

logger = logging.getLogger(__name__)


class RedisSessionData(TypedDict):
    user_id: str
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

    KEY_PREFIX = "session:"

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.rate_limit_storage_uri
        self.ttl_seconds = int(settings.access_token_expire_minutes) * 60

    async def create_session(
        self,
        jti: str,
        user_id: UUID,
        fingerprint: SessionFingerprint | None,
        mfa_verified_at: datetime | None,
    ) -> None:
        """Cache a newly created session in Redis."""
        if not self.redis_url:
            return

        key = f"{self.KEY_PREFIX}{jti}"
        now = datetime.now(UTC)

        data = {
            "user_id": str(user_id),
            "fingerprint_hash": fingerprint.fingerprint_hash if fingerprint else "",
            "mfa_verified_at": mfa_verified_at.isoformat() if mfa_verified_at else "",
            "last_seen_at": now.isoformat(),
            "created_at": now.isoformat(),
            "is_active": "1",
        }

        try:
            client = await _get_shared_client(self.redis_url)
            # Use HSET (Redis 4.0+)
            await client.hset(key, mapping=data)
            await client.expire(key, self.ttl_seconds)
        except (RedisError, OSError) as e:
            logger.warning(f"Failed to cache session {jti} in Redis: {e}")

    async def get_session(self, jti: str) -> RedisSessionData | None:
        """Retrieve session data from Redis."""
        if not self.redis_url:
            return None

        key = f"{self.KEY_PREFIX}{jti}"
        try:
            client = await _get_shared_client(self.redis_url)
            raw = await client.hgetall(key)
            if not raw:
                return None

            # Convert bytes to string if needed (redis-py decode_responses=False default in rate_limit)
            # rate_limit pool uses decode_responses=False
            data = {
                k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8")
                if isinstance(v, bytes)
                else v
                for k, v in raw.items()
            }

            return RedisSessionData(
                user_id=data.get("user_id", ""),
                fingerprint_hash=data.get("fingerprint_hash") or None,
                mfa_verified_at=data.get("mfa_verified_at") or None,
                last_seen_at=data.get("last_seen_at") or None,
                created_at=data.get("created_at", ""),
                is_active=data.get("is_active") == "1",
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
            client = await _get_shared_client(self.redis_url)
            # Fire and forget update
            await client.hset(key, "last_seen_at", now_str)
            # Refresh TTL
            await client.expire(key, self.ttl_seconds)
        except (RedisError, OSError):
            pass

    async def revoke_session(self, jti: str) -> None:
        """Remove session from Redis."""
        if not self.redis_url:
            return

        key = f"{self.KEY_PREFIX}{jti}"
        try:
            client = await _get_shared_client(self.redis_url)
            await client.delete(key)
        except (RedisError, OSError) as e:
            logger.warning(f"Failed to revoke session {jti} in Redis: {e}")
