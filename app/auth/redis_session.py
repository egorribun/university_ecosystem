from __future__ import annotations

import json
import logging

from app.core.logging import get_logger
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.deps.cache import RedisCache, get_cache

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class SessionBackend(ABC):
    @abstractmethod
    async def register_session(
        self,
        user_id: int,
        jti: str,
        expires_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def is_session_valid(self, jti: str) -> bool:
        pass

    @abstractmethod
    async def revoke_session(self, jti: str) -> None:
        pass


class RedisSessionBackend(SessionBackend):
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._prefix = "session:"

    async def register_session(
        self,
        user_id: int,
        jti: str,
        expires_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = f"{self._prefix}{jti}"
        now = datetime.now(UTC)
        ttl = int((expires_at - now).total_seconds())
        if ttl <= 0:
            return

        data = {
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
            **(metadata or {}),
        }
        await self._redis.set(key, json.dumps(data), ex=ttl)

    async def is_session_valid(self, jti: str) -> bool:
        key = f"{self._prefix}{jti}"
        return await self._redis.get(key) is not None

    async def revoke_session(self, jti: str) -> None:
        key = f"{self._prefix}{jti}"
        # P0-W5-03: Write the gateway's revocation blocklist key BEFORE deleting the
        # session, using the session's remaining TTL so the blocklist entry expires
        # at the same time the JWT would have expired naturally.
        remaining_ttl = await self._redis.ttl(key)  # -2 = not found, -1 = no TTL
        await self._redis.delete(key)
        if remaining_ttl > 0:
            revoked_key = f"revoked:jti:{jti}"
            await self._redis.set(revoked_key, "1", ex=remaining_ttl)
        # Notify Gateway to invalidate its L1 cache
        await self._redis.publish("session:revocations", jti)


async def get_session_backend() -> SessionBackend:
    if settings.session_storage_backend == "redis":
        cache = get_cache()
        if isinstance(cache, RedisCache):
            client = await cache._get_client()
            return RedisSessionBackend(client)

    class NullSessionBackend(SessionBackend):
        async def register_session(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def is_session_valid(self, jti: str) -> bool:
            return True

        async def revoke_session(self, jti: str) -> None:
            pass

    return NullSessionBackend()
