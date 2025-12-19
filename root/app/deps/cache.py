from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import logging
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import record_redis_command

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheEntry:
    etag: str
    payload: Any
    stored_at: float


class BaseCache:
    enabled: bool = False

    async def get(self, key: str) -> CacheEntry | None:
        raise NotImplementedError

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        raise NotImplementedError

    async def invalidate(self, *keys: str) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class NullCache(BaseCache):
    enabled = False

    async def get(self, key: str) -> CacheEntry | None:  # noqa: ARG002
        return None

    async def set(  # noqa: ARG002
        self,
        key: str,
        payload: Any,
        ttl: int | None = None,
    ) -> CacheEntry:
        return CacheEntry(
            etag="",
            payload=payload,
            stored_at=time_module.time(),
        )

    async def invalidate(self, *keys: str) -> None:  # noqa: ARG002
        return None


class MemoryCache(BaseCache):
    enabled = True

    def __init__(self, default_ttl: int = 0):
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._entries: dict[str, tuple[CacheEntry, float]] = {}

    async def get(self, key: str) -> CacheEntry | None:
        now = time_module.time()
        entry, expires_at = self._entries.get(key, (None, 0.0))
        if entry is None:
            return None
        if expires_at and expires_at <= now:
            await self.invalidate(key)
            return None
        return entry

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        stored_at = time_module.time()
        effective_ttl = self._resolve_ttl(ttl)
        expires_at = stored_at + effective_ttl if effective_ttl else 0.0
        entry = CacheEntry(etag=etag, payload=normalized_payload, stored_at=stored_at)
        self._entries[key] = (entry, expires_at)
        return entry

    async def invalidate(self, *keys: str) -> None:
        if not keys:
            return
        for key in keys:
            if "*" in key:
                for stored_key in list(self._entries.keys()):
                    if fnmatch.fnmatch(stored_key, key):
                        self._entries.pop(stored_key, None)
            else:
                self._entries.pop(key, None)

    def _resolve_ttl(self, ttl: int | None) -> int:
        if ttl is None:
            ttl = self._default_ttl
        ttl = int(ttl or 0)
        return ttl if ttl > 0 else 0


class RedisCache(BaseCache):
    enabled = True

    def __init__(self, url: str, default_ttl: int) -> None:
        self._url = url
        self._default_ttl = max(int(default_ttl or 0), 0)
        self._client: Redis | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                # Use robust connection pooling for Redis
                self._client = Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    retry_on_timeout=True,
                    max_connections=getattr(settings, "redis_pool_size", 20),
                )
        return self._client

    async def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        start = time_module.perf_counter()
        success = False
        try:
            await client.aclose()
            success = True
        except (RedisError, OSError):
            logger.debug("Failed to close Redis client", exc_info=True)
        finally:
            record_redis_command("close", time_module.perf_counter() - start, success=success)

    async def get(self, key: str) -> CacheEntry | None:
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            raw = await client.get(key)
            if raw is None:
                return None
            parsed = json.loads(raw)
            etag = str(parsed.get("etag", ""))
            payload = parsed.get("payload")
            stored_at = float(parsed.get("stored_at") or 0.0)
            if not stored_at:
                stored_at = time_module.time()
            if not etag:
                return None
            success = True
            return CacheEntry(etag=etag, payload=payload, stored_at=stored_at)
        except json.JSONDecodeError:
            logger.debug("Invalid cache payload for key %s, dropping", key)
            await self.invalidate(key)
            return None
        except (RedisError, OSError):
            logger.warning("Redis cache get failed for key %s", key, exc_info=True)
            return None
        finally:
            record_redis_command("get", time_module.perf_counter() - start, success=success)

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        envelope = json.dumps(
            {
                "etag": etag,
                "payload": normalized_payload,
                "stored_at": time_module.time(),
            },
            ensure_ascii=False,
        )
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()
            expire = self._resolve_ttl(ttl)
            if expire:
                await client.set(key, envelope, ex=expire)
            else:
                await client.set(key, envelope)
            success = True
        except (RedisError, OSError):
            logger.warning("Redis cache set failed for key %s", key, exc_info=True)
        finally:
            record_redis_command("set", time_module.perf_counter() - start, success=success)
        return CacheEntry(etag=etag, payload=normalized_payload, stored_at=time_module.time())

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(key) for key in keys if key]
        if not filtered:
            return
        start = time_module.perf_counter()
        success = False
        try:
            client = await self._get_client()

            # Separate exact keys and patterns
            exact_keys = []
            patterns = []
            for key in filtered:
                if "*" in key:
                    patterns.append(key)
                else:
                    exact_keys.append(key)

            # Delete exact keys
            if exact_keys:
                await client.delete(*exact_keys)

            # Process patterns
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, matches = await client.scan(cursor, match=pattern, count=100)
                    if matches:
                        await client.delete(*matches)
                    if cursor == 0:
                        break
            success = True
        except (RedisError, OSError):
            logger.warning("Redis cache invalidate failed for keys %s", filtered, exc_info=True)
        finally:
            record_redis_command(
                "invalidate",
                time_module.perf_counter() - start,
                success=success,
            )

    def _resolve_ttl(self, ttl: int | None) -> int:
        if ttl is None:
            ttl = self._default_ttl
        ttl = int(ttl or 0)
        return ttl if ttl > 0 else 0


_cache_backend: BaseCache | None = None


def _normalize_payload(payload: Any) -> tuple[Any, bytes]:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    )
    normalized = json.loads(serialized) if serialized else payload
    return normalized, serialized.encode("utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return str(value)


def create_cache_backend() -> BaseCache:
    if not settings.cache_enabled:
        return NullCache()

    backend = getattr(settings, "cache_backend_normalized", None) or getattr(
        settings, "cache_backend", "redis"
    )
    backend = str(backend).strip().lower()
    ttl = int(getattr(settings, "cache_default_ttl_seconds", 0) or 0)

    if backend == "memory":
        return MemoryCache(default_ttl=ttl)

    if backend != "redis":
        return NullCache()

    url = (settings.cache_redis_url or "").strip()
    if not url:
        return NullCache()

    return RedisCache(url=url, default_ttl=ttl)


def get_cache() -> BaseCache:
    global _cache_backend
    if _cache_backend is None:
        _cache_backend = create_cache_backend()
    return _cache_backend


def set_cache_backend(cache: BaseCache | None) -> None:
    global _cache_backend
    _cache_backend = cache


async def shutdown_cache() -> None:
    global _cache_backend
    backend = _cache_backend
    _cache_backend = None
    if backend and isinstance(backend, RedisCache):
        await backend.close()


def format_etag(etag: str) -> str:
    if not etag:
        return etag
    etag = etag.strip()
    if etag.startswith('"') and etag.endswith('"'):
        return etag
    return f'"{etag}"'


def etag_matches(etag: str, header_value: str | None) -> bool:
    if not etag or not header_value:
        return False
    candidate = etag.strip()
    parts = header_value.split(",")
    for part in parts:
        item = part.strip()
        if not item:
            continue
        if item == "*":
            return True
        if item.startswith("W/"):
            item = item[2:].strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1]
        if item == candidate:
            return True
    return False


__all__ = [
    "CacheEntry",
    "BaseCache",
    "NullCache",
    "MemoryCache",
    "RedisCache",
    "create_cache_backend",
    "get_cache",
    "set_cache_backend",
    "shutdown_cache",
    "format_etag",
    "etag_matches",
]
