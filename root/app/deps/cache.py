from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheEntry:
    etag: str
    payload: Any


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
        return CacheEntry(etag="", payload=payload)

    async def invalidate(self, *keys: str) -> None:  # noqa: ARG002
        return None


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
                self._client = Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30,
                )
        return self._client

    async def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        try:
            await client.aclose()
        except (RedisError, OSError):
            logger.debug("Failed to close Redis client", exc_info=True)

    async def get(self, key: str) -> CacheEntry | None:
        try:
            client = await self._get_client()
            raw = await client.get(key)
        except (RedisError, OSError):
            logger.warning("Redis cache get failed for key %s", key, exc_info=True)
            return None
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Invalid cache payload for key %s, dropping", key)
            await self.invalidate(key)
            return None
        etag = str(parsed.get("etag", ""))
        payload = parsed.get("payload")
        if not etag:
            return None
        return CacheEntry(etag=etag, payload=payload)

    async def set(self, key: str, payload: Any, ttl: int | None = None) -> CacheEntry:
        normalized_payload, serialized = _normalize_payload(payload)
        etag = hashlib.sha256(serialized).hexdigest()
        envelope = json.dumps(
            {"etag": etag, "payload": normalized_payload}, ensure_ascii=False
        )
        try:
            client = await self._get_client()
            expire = self._resolve_ttl(ttl)
            if expire:
                await client.set(key, envelope, ex=expire)
            else:
                await client.set(key, envelope)
        except (RedisError, OSError):
            logger.warning("Redis cache set failed for key %s", key, exc_info=True)
        return CacheEntry(etag=etag, payload=normalized_payload)

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(key) for key in keys if key]
        if not filtered:
            return
        try:
            client = await self._get_client()
            await client.delete(*filtered)
        except (RedisError, OSError):
            logger.warning(
                "Redis cache invalidate failed for keys %s", filtered, exc_info=True
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
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def create_cache_backend() -> BaseCache:
    if not settings.cache_enabled:
        return NullCache()
    url = settings.cache_redis_url_effective.strip()
    if not url:
        return NullCache()
    ttl = int(getattr(settings, "cache_default_ttl_seconds", 0) or 0)
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
    "RedisCache",
    "create_cache_backend",
    "get_cache",
    "set_cache_backend",
    "shutdown_cache",
    "format_etag",
    "etag_matches",
]
