from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger
from app.deps.cache import RedisCache, get_cache

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class SessionBackend(ABC):
    @abstractmethod
    async def register_session(
        self,
        # LOW-W19: user_id is typed int | str because the rest of the codebase
        # uses UUID strings (str) as primary keys; int is kept for backwards
        # compatibility with any legacy integer-keyed callers.
        user_id: int | str,
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
    def __init__(self, redis_client: Redis[Any]) -> None:
        self._redis = redis_client
        self._prefix = "session:"

    async def register_session(
        self,
        user_id: int | str,
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
        revoked_key = f"revoked:jti:{jti}"
        # RZ-W19-12: atomize TTL-read + delete + revoked-key-write via Lua script
        # to close the TOCTOU race window where a revoked session appears valid.
        lua_script = """
        local ttl = redis.call('TTL', KEYS[1])
        redis.call('DEL', KEYS[1])
        if ttl > 0 then
            redis.call('SET', KEYS[2], '1', 'EX', ttl)
        end
        return ttl
        """
        try:
            await self._redis.eval(lua_script, 2, key, revoked_key)  # type: ignore[no-untyped-call]
        except Exception as exc:
            from redis.exceptions import ResponseError

            if isinstance(exc, (ConnectionError, TimeoutError, OSError, ResponseError)):
                # RZ-25-06: Use pipeline to minimize TOCTOU window when Lua unavailable.
                remaining_ttl = await self._redis.ttl(key)
                if remaining_ttl > 0:
                    pipe = self._redis.pipeline(transaction=True)
                    pipe.delete(key)
                    pipe.set(revoked_key, "1", ex=remaining_ttl)
                    await pipe.execute()
                else:
                    await self._redis.delete(key)
            else:
                raise
        # Notify Gateway to invalidate its L1 cache
        try:
            await self._redis.publish("session:revocations", jti)
        except (
            ConnectionError,
            TimeoutError,
            OSError,
        ):  # RZ-22-01: narrowed — Redis pub/sub errors
            logger.warning("Failed to publish session revocation for jti=%s", jti)


async def get_session_backend() -> SessionBackend:
    if settings.session_storage_backend == "redis":
        cache = get_cache()
        if isinstance(cache, RedisCache):
            client = await cache._get_client()
            return RedisSessionBackend(client)
        # RZ-25-02: Fail-closed in production — NullSessionBackend bypasses revocation.
        _env = getattr(settings, "environment", "production").lower()
        if _env not in {"development", "local", "testing", "test"}:
            raise RuntimeError(
                "Session storage backend is 'redis' but Redis cache is unavailable. "
                "NullSessionBackend would bypass session revocation — refusing to start. "
                "Check REDIS_URL configuration."
            )

    class NullSessionBackend(SessionBackend):
        # LOW-W19: tracks whether the first-use warning has been emitted
        # so we don't flood logs on every is_session_valid call.
        _warned: bool = False

        async def register_session(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def is_session_valid(self, jti: str) -> bool:
            # LOW-W19: NullSessionBackend always returns True, which means
            # revoked tokens are never rejected.  Warn once so operators know
            # session validation is effectively disabled in this environment.
            if not NullSessionBackend._warned:
                NullSessionBackend._warned = True
                logger.warning(
                    "NullSessionBackend in use — is_session_valid always returns True; "
                    "session revocation is disabled.  Configure a Redis backend in production."
                )
            return True

        async def revoke_session(self, jti: str) -> None:
            pass

    return NullSessionBackend()
