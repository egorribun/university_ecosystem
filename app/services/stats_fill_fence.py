from __future__ import annotations

import hashlib
import math
import re
import secrets
import time
from typing import TYPE_CHECKING, Any, cast

from nats.js.api import Header
from nats.js.errors import (
    APIError,
    KeyNotFoundError,
    KeyWrongLastSequenceError,
    NotFoundError,
)
from nats.js.kv import KV_DEL, KV_OP, KV_PURGE
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, WatchError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.logging import get_logger
from app.core.metrics import record_redis_command
from app.deps import cache as cache_module
from app.deps.cache import (
    _NATS_CACHE_UNAVAILABLE_ERRORS,
    CacheEntry,
    MemoryCache,
    NatsKVCache,
    RedisCache,
    TieredCache,
    _cache_key_fingerprint,
    _encode_kv_key,
    _missing_nats_bucket,
    _normalize_payload,
)

if TYPE_CHECKING:
    from app.deps.cache import BaseCache

logger = get_logger(__name__)
_json: Any = vars(cache_module)["orjson"]
_MARKER = "~stats-fill-v1:"
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")
_MAX_RESERVATION_TTL = 30
_MAX_TTL = 2**31 - 1
_NATS_BARRIER = "stats:__fill_fence_barrier__"


def _ack_matches(ack: Any, stream: str) -> bool:
    return (
        getattr(ack, "stream", None) == stream
        and type(getattr(ack, "seq", None)) is int
        and ack.seq > 0
        and hasattr(ack, "duplicate")
        and (ack.duplicate is None or ack.duplicate is False)
    )


def _nats_binding(cache: NatsKVCache, kv: Any) -> tuple[str, str] | None:
    stream = "KV_" + cache._bucket_name
    prefix = f"$KV.{cache._bucket_name}."
    if kv._stream != stream or kv._pre != prefix:
        return None
    return stream, prefix


async def _nats_leader_last(kv: Any, stream: str, subject: str) -> Any:
    try:
        return await kv._js.get_msg(stream, subject=subject, direct=False)
    except NotFoundError as exc:
        if exc.code == 404 and exc.err_code == 10037:
            return None
        raise


def _nats_live_tombstone(data: Any) -> bool:
    try:
        marker: object = _json.loads(data)
    except (TypeError, ValueError):
        return False
    if not isinstance(marker, dict):
        return False
    payload = marker.get("payload")
    stored = marker.get("stored_at")
    ttl = marker.get("ttl_seconds")
    if (
        not isinstance(stored, (int, float))
        or isinstance(stored, bool)
        or not isinstance(ttl, (int, float))
        or isinstance(ttl, bool)
    ):
        return False
    if (
        not isinstance(payload, str)
        or not payload.startswith(_MARKER)
        or _TOKEN.fullmatch(payload[len(_MARKER) :]) is None
        or marker.get("etag") != _entry(payload, 1)[0].etag
        or not math.isfinite(stored)
        or not math.isfinite(ttl)
        or not 0 < ttl <= _MAX_RESERVATION_TTL
    ):
        return False
    now = time.time()
    return stored <= now + _MAX_RESERVATION_TTL and now < stored + ttl


def _valid(key: str, token: str, ttl: int, maximum: int) -> bool:
    return (
        isinstance(key, str)
        and bool(key)
        and isinstance(token, str)
        and _TOKEN.fullmatch(token) is not None
        and type(ttl) is int
        and 0 < ttl <= maximum
    )


def _entry(
    payload: object, ttl: int, *, reservation: bool = False
) -> tuple[CacheEntry, str]:
    normalized, serialized = _normalize_payload(payload)
    entry = CacheEntry(
        etag=hashlib.sha256(serialized).hexdigest(),
        payload=normalized,
        # A Redis marker must not be promoted into a TieredCache L1. Its
        # physical lifetime is still controlled by SET EX, not this metadata.
        stored_at=1.0 if reservation else time.time(),
        ttl_seconds=1.0 if reservation else float(ttl),
    )
    raw: bytes = _json.dumps(
        {
            "etag": entry.etag,
            "payload": entry.payload,
            "stored_at": entry.stored_at,
            "ttl_seconds": entry.ttl_seconds,
        }
    )
    return entry, raw.decode("utf-8")


def _redis_backend(cache: BaseCache) -> RedisCache | None:
    if type(cache) is RedisCache:
        return cache
    if type(cache) is TieredCache:
        tiered = cache
        if type(tiered.l1) is MemoryCache and type(tiered.l2) is RedisCache:
            return tiered.l2
    return None


def _watch_transport(exc: WatchError) -> BaseException | None:
    """Follow the visible exception chain without treating contention as failure."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (RedisConnectionError, RedisTimeoutError, OSError)):
            return current
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return None


async def _nats_reserve(
    cache: NatsKVCache, key: str, token: str, raw: str, ttl: int
) -> bool | None:
    try:
        kv = await cache._get_kv()
        ttl_enabled = (await kv.status()).stream_info.config.allow_msg_ttl
        if ttl_enabled is True:
            await kv.create(_encode_kv_key(key), raw.encode("utf-8"), msg_ttl=ttl)
            return True
        if ttl_enabled is not False:
            return None
        binding = _nats_binding(cache, kv)
        if binding is None:
            return None
        stream, prefix = binding
        subject = prefix + _encode_kv_key(key)
        current = await _nats_leader_last(kv, stream, subject)
        revision = 0
        if current is not None:
            if (
                current.subject != subject
                or type(current.seq) is not int
                or current.seq <= 0
            ):
                return None
            if (current.headers or {}).get(KV_OP) not in (KV_DEL, KV_PURGE):
                return False
            if _nats_live_tombstone(current.data):
                return False
            revision = current.seq
        _, leased_raw = _entry(_MARKER + token, ttl)
        ack = await kv._js.publish(
            subject,
            leased_raw.encode("utf-8"),
            stream=stream,
            headers={
                KV_OP: KV_DEL,
                Header.EXPECTED_LAST_SUBJECT_SEQUENCE: str(revision),
            },
        )
        return True if _ack_matches(ack, stream) else None
    except KeyWrongLastSequenceError:
        return False
    except KeyNotFoundError:
        return None
    except _NATS_CACHE_UNAVAILABLE_ERRORS as exc:
        if isinstance(exc, NotFoundError) and not _missing_nats_bucket(exc):
            raise
        logger.warning(
            "NATS KV stats reservation failed",
            cache_key_fingerprint=_cache_key_fingerprint(key),
            error_type=type(exc).__name__,
        )
        return None
    except APIError as exc:
        if exc.err_code in (10071, 10164):
            return False
        if exc.code in (401, 403):
            return None
        raise


async def _nats_complete(
    cache: NatsKVCache, key: str, token: str, marker_tag: str, raw: str
) -> bool | None:
    try:
        kv = await cache._get_kv()
        ttl_enabled = (await kv.status()).stream_info.config.allow_msg_ttl
        if ttl_enabled is not True and ttl_enabled is not False:
            return None
        binding = _nats_binding(cache, kv)
        if binding is None:
            return None
        stream, prefix = binding
        subject = prefix + _encode_kv_key(key)
        barrier_id = secrets.token_hex(16)
        ack = await kv._js.publish(
            prefix + _encode_kv_key(_NATS_BARRIER),
            b"",
            stream=stream,
            headers={KV_OP: KV_DEL, Header.MSG_ID: barrier_id},
        )
        if not _ack_matches(ack, stream):
            return None
        current = await _nats_leader_last(kv, stream, subject)
        if current is None:
            return False
        try:
            marker: object = _json.loads(current.data)
        except (TypeError, ValueError):
            return False
        revision = current.seq
        operation = (current.headers or {}).get(KV_OP)
        if (
            current.subject != subject
            or not isinstance(marker, dict)
            or marker.get("payload") != _MARKER + token
            or marker.get("etag") != marker_tag
            or type(revision) is not int
            or revision <= 0
            or (ttl_enabled is False and operation != KV_DEL)
            or (ttl_enabled is False and not _nats_live_tombstone(current.data))
            or (ttl_enabled is True and operation is not None)
        ):
            return False
        ack = await kv._js.publish(
            subject,
            raw.encode("utf-8"),
            stream=stream,
            headers={
                Header.EXPECTED_LAST_SUBJECT_SEQUENCE: str(revision),
                Header.EXPECTED_LAST_MSG_ID: barrier_id,
            },
        )
        return True if _ack_matches(ack, stream) else None
    except KeyWrongLastSequenceError:
        return False
    except _NATS_CACHE_UNAVAILABLE_ERRORS as exc:
        if isinstance(exc, NotFoundError) and not _missing_nats_bucket(exc):
            raise
        logger.warning(
            "NATS KV stats completion failed",
            cache_key_fingerprint=_cache_key_fingerprint(key),
            error_type=type(exc).__name__,
        )
        return None
    except APIError as exc:
        if exc.err_code in (10070, 10071, 10164):
            return False
        if exc.code in (401, 403):
            return None
        raise


class StatsFillFence:
    """Fence one stats key; a fresh random token is required for every attempt.

    Memory safety is process-local and requires one event loop. For TieredCache,
    the Redis L2 is authoritative and L1 is populated only by normal read-through.
    NATS marker completion uses an authoritative read and a global barrier.
    Successful legacy invalidation and guarded writers are prerequisites; this
    adapter cannot repair failed deletes or an older unconditional writer.
    """

    def __init__(self, cache: BaseCache) -> None:
        self.cache = cache

    @property
    def supported(self) -> bool:
        """Report backend-type support; NATS stream TTL is checked per operation."""
        return (
            type(self.cache) in (MemoryCache, NatsKVCache)
            or _redis_backend(self.cache) is not None
        )

    async def reserve(self, key: str, token: str, ttl: int) -> bool | None:
        """Return None for unsupported or unknown outcomes, never permission to set."""
        backend = self.cache
        redis_cache = _redis_backend(backend)
        if (
            type(backend) not in (MemoryCache, NatsKVCache) and redis_cache is None
        ) or not _valid(key, token, ttl, _MAX_RESERVATION_TTL):
            return None
        marker, raw = _entry(
            _MARKER + token,
            ttl,
            reservation=redis_cache is not None or type(backend) is NatsKVCache,
        )
        if type(backend) is MemoryCache:
            cache = backend
            now = time.time()
            slot = cache._entries.get(key)
            if slot is not None:
                _, deadline = slot
                if deadline and deadline <= now:
                    cache._entries.pop(key, None)
                else:
                    return False
            cache._store_entry(key, marker, now + ttl)
            return True
        if type(backend) is NatsKVCache:
            return await _nats_reserve(backend, key, token, raw, ttl)
        redis_cache = cast("RedisCache", redis_cache)
        start = time.perf_counter()
        success = False
        try:
            client = await redis_cache._get_client()
            reserved = bool(await client.set(key, raw, nx=True, ex=ttl))
            success = True
            return reserved
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis stats reservation failed",
                cache_key_fingerprint=_cache_key_fingerprint(key),
                error_type=type(exc).__name__,
            )
            return None
        finally:
            record_redis_command("set", time.perf_counter() - start, success=success)

    async def complete(
        self, key: str, token: str, payload: object, ttl: int
    ) -> bool | None:
        """Write only if the caller still owns the live marker in the same key."""
        backend = self.cache
        redis_cache = _redis_backend(backend)
        if (
            (type(backend) not in (MemoryCache, NatsKVCache) and redis_cache is None)
            or not _valid(key, token, ttl, _MAX_TTL)
            or not isinstance(payload, dict)
        ):
            return None
        value, raw = _entry(payload, ttl)
        marker_tag = _entry(_MARKER + token, 1)[0].etag
        if type(backend) is MemoryCache:
            cache = backend
            now = time.time()
            slot = cache._entries.get(key)
            if slot is None:
                return False
            entry, deadline = slot
            if not deadline or deadline <= now:
                if deadline and deadline <= now:
                    cache._entries.pop(key, None)
                return False
            if entry.payload != _MARKER + token or entry.etag != marker_tag:
                return False
            cache._store_entry(key, value, now + ttl)
            return True
        if type(backend) is NatsKVCache:
            return await _nats_complete(backend, key, token, marker_tag, raw)
        redis_cache = cast("RedisCache", redis_cache)
        start = time.perf_counter()
        success = False
        try:
            client = await redis_cache._get_client()
            async with client.pipeline(transaction=True) as pipe:
                await pipe.watch(key)
                old = await pipe.get(key)
                if old is None:
                    success = True
                    return False
                try:
                    current: object = _json.loads(old)
                except (ValueError, TypeError):
                    success = True
                    return False
                if (
                    not isinstance(current, dict)
                    or current.get("payload") != _MARKER + token
                    or current.get("etag") != marker_tag
                ):
                    success = True
                    return False
                if await pipe.pttl(key) <= 0:
                    success = True
                    return False
                pipe.multi()
                pipe.set(key, raw, ex=ttl)
                await pipe.execute()
                success = True
                return True
        except WatchError as exc:
            transport = _watch_transport(exc)
            if transport is not None:
                logger.warning(
                    "Redis stats completion failed",
                    cache_key_fingerprint=_cache_key_fingerprint(key),
                    error_type=type(transport).__name__,
                )
                return None
            success = True
            return False
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis stats completion failed",
                cache_key_fingerprint=_cache_key_fingerprint(key),
                error_type=type(exc).__name__,
            )
            return None
        finally:
            record_redis_command("set", time.perf_counter() - start, success=success)
