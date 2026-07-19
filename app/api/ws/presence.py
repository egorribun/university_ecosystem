"""Presence pub/sub, audience cache, and online-status helpers.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from the monolithic
app/api/websocket.py to enforce SRP.  This module owns:
  - In-memory LRU TTL presence cache (OrderedDict, capped at 10 000 entries)
  - Redis pub/sub bridge (PresencePubSub)
  - Public cache-invalidation helpers
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.core.protocols import AsyncDatabaseSession
    from app.schemas.chat import PresenceStatus

from redis.asyncio import Redis

from app.core.config import settings
from app.core.database import async_session
from app.deps.cache import get_cache, versioned_key
from app.repositories.chat_repository import ChatRepository

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

PRESENCE_SOURCE_CONNECT = "connect"
PRESENCE_SOURCE_DISCONNECT = "disconnect"
PRESENCE_SOURCE_PING = "ping"
PRESENCE_SOURCE_PUBSUB = "pubsub"

_PRESENCE_INSTANCE_ID = uuid.uuid4().hex

# ── In-memory LRU cache ───────────────────────────────────────────────────────
# PERF-07 (audit 2026-03-04): Capped OrderedDict prevents OOM under unbounded
# presence checks when Redis is unavailable.
_PRESENCE_DB_CACHE: OrderedDict[uuid.UUID, tuple[set[uuid.UUID], float]] = OrderedDict()
_PRESENCE_DB_CACHE_TTL = 30.0  # seconds
_PRESENCE_DB_CACHE_MAX_SIZE = 10_000
# PERF-4 (audit 2026-03-05): Eagerly initialised asyncio.Lock — always safe
# because this module is imported during lifespan startup.
_PRESENCE_DB_CACHE_LOCK: asyncio.Lock = asyncio.Lock()


def _get_presence_cache_lock() -> asyncio.Lock:
    return _PRESENCE_DB_CACHE_LOCK


# ── Audience resolution ───────────────────────────────────────────────────────


async def _get_presence_audience(user_id: uuid.UUID) -> set[uuid.UUID]:
    """Resolve user IDs that should receive presence updates for user_id."""
    cache = get_cache()
    cache_key = versioned_key(f"user:{user_id}:presence_audience")

    if cache.enabled:
        entry = await cache.get(cache_key)
        if entry:
            return set(entry.payload)

    loop = asyncio.get_running_loop()
    now = loop.time()
    cached = _PRESENCE_DB_CACHE.get(user_id)
    if cached is not None:
        _PRESENCE_DB_CACHE.move_to_end(user_id)
        if (now - cached[1]) < _PRESENCE_DB_CACHE_TTL:
            return cached[0]

    async with _get_presence_cache_lock():
        # Refresh timestamp after potentially waiting for the lock; the stale
        # pre-lock `now` could let an expired entry pass the TTL check.
        now = loop.time()
        cached = _PRESENCE_DB_CACHE.get(user_id)
        if cached is not None:
            _PRESENCE_DB_CACHE.move_to_end(user_id)
            if (now - cached[1]) < _PRESENCE_DB_CACHE_TTL:
                return cached[0]

        async with async_session() as session:
            repo = ChatRepository(session)
            audience = await repo.get_presence_audience(user_id)

        _PRESENCE_DB_CACHE[user_id] = (audience, loop.time())
        if len(_PRESENCE_DB_CACHE) > _PRESENCE_DB_CACHE_MAX_SIZE:
            _PRESENCE_DB_CACHE.popitem(last=False)

    if cache.enabled:
        await cache.set(cache_key, list(audience), ttl=3600)

    return audience


async def invalidate_presence_audience_cache(*user_ids: uuid.UUID) -> None:
    """Invalidate presence audience cache for one or more users."""
    cache = get_cache()
    if not cache.enabled or not user_ids:
        return
    keys = [versioned_key(f"user:{uid}:presence_audience") for uid in user_ids]
    await cache.invalidate(*keys)


async def invalidate_chat_participants_cache(chat_id: uuid.UUID) -> None:
    """Invalidate participants cache for a specific chat."""
    cache = get_cache()
    if not cache.enabled:
        return
    await cache.invalidate(versioned_key(f"chat:{chat_id}:participants"))


# ── PresencePubSub ────────────────────────────────────────────────────────────


class PresencePubSub:
    """Optional Redis pub/sub bridge for presence events."""

    def __init__(self) -> None:
        self._redis: Redis[Any] | None = None
        self._pubsub_task: asyncio.Task[Any] | None = None

    async def initialize(self, redis: Redis[Any] | None = None) -> None:
        if self._redis or not settings.presence_pubsub_enabled:
            return
        if redis is not None:
            self._redis = redis
        elif settings.cache_redis_url:
            from app.deps.cache import get_cache_client

            try:
                self._redis = await get_cache_client()
            except (
                ConnectionError,
                TimeoutError,
                OSError,
            ) as exc:  # RZ-22-01: narrowed — Redis connection errors
                logger.warning(
                    "Failed to share Redis client for presence pub/sub: %s", exc
                )
                self._redis = Redis.from_url(
                    settings.cache_redis_url,
                    decode_responses=True,
                    max_connections=getattr(settings, "redis_pool_size", 20),
                )
        if self._redis:
            self._pubsub_task = asyncio.create_task(self._listen_for_updates())

    async def shutdown(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
        self._pubsub_task = None

    async def publish(self, payload: dict[str, Any]) -> None:
        if not self._redis or not settings.presence_pubsub_enabled:
            return
        envelope = dict(payload)
        envelope["instance_id"] = _PRESENCE_INSTANCE_ID
        await self._redis.publish(
            settings.presence_pubsub_channel, json.dumps(envelope, default=str)
        )

    async def _listen_for_updates(self) -> None:
        # Use the locally moved _handle_presence_pubsub
        # (manager is imported lazily inside it)

        if not self._redis:
            return
        ps = self._redis.pubsub()
        await ps.subscribe(settings.presence_pubsub_channel)
        try:
            async for message in ps.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                try:
                    payload = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    logger.warning("Invalid presence payload received from pubsub")
                    continue
                if payload.get("instance_id") == _PRESENCE_INSTANCE_ID:
                    continue
                await _handle_presence_pubsub(payload)
        except asyncio.CancelledError:
            if ps:
                await ps.unsubscribe(settings.presence_pubsub_channel)
                await ps.close()
        except (
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:  # RZ-22-01: narrowed — Redis pub/sub errors
            logger.error("Presence Pub/Sub listener error: %s", exc)


async def _handle_presence_pubsub(payload: dict[str, Any]) -> None:
    """Handle a presence update received from Redis pub/sub.

    RZ-07 (audit 2026-03-04): Validate the user_id from the payload before
    broadcasting.  A misconfigured or compromised Redis channel could inject
    arbitrary user_ids, spoofing presence for any user's contacts.
    Only forward updates for users who already have an active connection on
    this pod.
    """
    from datetime import datetime

    from app.api.ws.connection_manager import manager

    try:
        raw_user_id = payload.get("user_id")
        if not raw_user_id:
            return
        user_id = uuid.UUID(str(raw_user_id))
    except (ValueError, AttributeError):# RZ-28-01
        logger.warning("presence pubsub: invalid user_id in payload")
        return

    if not manager.is_online(user_id):
        return

    active = bool(payload.get("active", False))
    last_seen_raw = payload.get("last_seen")
    try:
        last_seen = datetime.fromisoformat(last_seen_raw) if last_seen_raw else None
    except ValueError:
        last_seen = None

    await manager.broadcast_presence(
        user_id,
        active,
        last_seen,
        source=PRESENCE_SOURCE_PUBSUB,
        force=True,
        publish=False,
    )


presence_pubsub = PresencePubSub()


async def build_presence_map(
    user_ids: Iterable[uuid.UUID],
    db: AsyncDatabaseSession | None = None,
) -> dict[uuid.UUID, PresenceStatus]:
    """Return presence info for a set of users.

    Accepts an optional open DB session (request-scoped callers) or opens
    its own session (background tasks / non-request contexts).
    """
    # Lazy import avoids a circular dependency with connection_manager.
    from app.api.ws.connection_manager import manager

    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}

    from app.repositories.session_repository import SessionRepository
    from app.schemas.chat import PresenceStatus

    if db:
        repo = SessionRepository(db)
        last_seen_map = await repo.get_last_seen_map(list(ids))
    else:
        async with async_session() as new_session:
            repo = SessionRepository(new_session)
            last_seen_map = await repo.get_last_seen_map(list(ids))

    return {
        uid: PresenceStatus(
            active=manager.is_online(uid),
            last_seen_at=last_seen_map.get(uid),
        )
        for uid in ids
    }


async def start_presence_pubsub() -> None:
    """Initialize the presence pub/sub bridge."""
    await presence_pubsub.initialize()


async def stop_presence_pubsub() -> None:
    """Shut down the presence pub/sub bridge."""
    await presence_pubsub.shutdown()
