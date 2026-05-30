"""WebSocket connection management — ConnectionManager and rate limiter.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: connection lifecycle and per-connection rate limiting.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakValueDictionary

from fastapi import Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import record_presence_event, record_presence_throttled
from app.deps.cache import get_cache, versioned_key
from app.repositories.chat_repository import ChatRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)


class WebSocketRateLimiter:
    """Token Bucket rate limiter for WebSocket messages. (Audit 6.3)

    Prevents DoS flooding by limiting message arrival rate per connection.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        # Lazy init: asyncio.get_event_loop() raises in Python 3.12+ outside a loop.
        self.last_update: float = 0.0

    def consume(self) -> bool:
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self.last_update == 0.0:
            self.last_update = now
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# PERF-W15-02 (audit 2026-03-23 Wave 15): Per-room broadcast semaphores.
#
# Previously a single global Semaphore(100) was shared across ALL rooms.
# A slow room (1000 participants) could occupy all 100 slots, causing
# Head-of-Line blocking for fast rooms (2 participants).
#
# Fix: each chat room gets its own Semaphore(_MAX_CONCURRENT_SENDS_PER_ROOM).
# A slow room can hold at most 5 slots; all other rooms are unaffected.
#
# Presence broadcasts use a separate global semaphore — they are not per-room
# (audience spans multiple rooms) so per-room isolation does not apply.
_MAX_CONCURRENT_SENDS_PER_ROOM: int = 5
_room_semaphores: dict[str, asyncio.Semaphore] = {}
_room_semaphores_lock: asyncio.Lock | None = None  # Lazy: created inside event loop

# Presence fan-out: separate semaphore, not per-room.
# LOW-W19: asyncio.Semaphore must be created inside a running event loop.
# Module-level instantiation breaks when the module is imported outside of an
# async context (e.g. CLI scripts, pytest collection) on Python 3.10+.
# Use lazy init: the sentinel is None; _get_presence_semaphore() creates it on
# first call from inside a running loop (i.e. a live request or test coroutine).
_PRESENCE_SEMAPHORE: asyncio.Semaphore | None = None


def _get_presence_semaphore() -> asyncio.Semaphore:
    """Return (or lazily create) the presence fan-out semaphore."""
    global _PRESENCE_SEMAPHORE
    if _PRESENCE_SEMAPHORE is None:
        _PRESENCE_SEMAPHORE = asyncio.Semaphore(20)
    return _PRESENCE_SEMAPHORE


def _get_room_semaphores_lock() -> asyncio.Lock:
    """Lazy-initialise the room semaphores dict lock (must run inside event loop)."""
    global _room_semaphores_lock
    if _room_semaphores_lock is None:
        _room_semaphores_lock = asyncio.Lock()
    return _room_semaphores_lock


async def _get_room_semaphore(room_key: str) -> asyncio.Semaphore:
    """Return the per-room semaphore for *room_key*, creating it if needed.

    Uses double-checked locking to avoid acquiring the dict lock on every call.
    """
    sem = _room_semaphores.get(room_key)
    if sem is not None:
        return sem
    async with _get_room_semaphores_lock():
        # Re-check inside the lock — another coroutine may have raced us.
        sem = _room_semaphores.get(room_key)
        if sem is None:
            sem = asyncio.Semaphore(_MAX_CONCURRENT_SENDS_PER_ROOM)
            _room_semaphores[room_key] = sem
    return sem


async def cleanup_room_semaphores(active_room_keys: set[str]) -> None:
    """Remove semaphores for rooms with no active connections (GC helper).

    Call this periodically from the app lifespan to prevent unbounded dict growth.
    Rooms that still have connections retain their semaphore; stale ones are dropped.
    """
    stale = set(_room_semaphores) - active_room_keys
    for key in stale:
        _room_semaphores.pop(key, None)
    if stale:
        logger.debug("Cleaned up %d stale room semaphores", len(stale))


class ConnectionManager:
    """Manages WebSocket connections for all users."""

    MAX_CONNECTIONS_PER_USER: int = 5

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.active_connections: dict[uuid.UUID, set[WebSocket]] = {}
        self.connection_users: dict[WebSocket, uuid.UUID] = {}
        self.rate_limiters: dict[WebSocket, WebSocketRateLimiter] = {}
        self._last_presence_sent_at: dict[uuid.UUID, datetime] = {}
        # PERF-4 (audit 2026-03-05): Eagerly initialised asyncio.Lock — always safe
        # because ConnectionManager is instantiated inside lifespan startup.
        self._lock: asyncio.Lock = asyncio.Lock()
        # RZ-14-05 (audit Wave 14): Inject session factory via constructor to
        # avoid bypassing Dishka DI.  Falls back to global async_session when
        # no factory is injected (backward compatibility).
        self._session_factory = session_factory
        # RZ-14-04 (audit 2026-03-23): Changed dict → WeakValueDictionary.
        # dict[uuid.UUID, asyncio.Lock] accumulated one entry per chat_id for
        # the entire lifetime of the process — an O(distinct_chats_ever) memory
        # leak.  WeakValueDictionary automatically evicts entries once no
        # coroutine holds a reference to the Lock (i.e. no async with is active
        # for that chat_id).  asyncio.Lock IS weakly-referenceable.
        # PERF-14-03 (audit Wave 14): Per-chat locks for single-flight cache
        # miss coalescing — prevents N concurrent broadcast_to_chat calls from
        # each opening a separate DB session on the same cache miss.
        self._participant_locks: WeakValueDictionary[uuid.UUID, asyncio.Lock] = (
            WeakValueDictionary()
        )

    def _get_lock(self) -> asyncio.Lock:
        return self._lock

    # TD-14-03 (audit Wave 14): Extracted shared disconnect logic.  Both
    # disconnect() and send_to_user() dead-connection cleanup used identical
    # code.  This method MUST be called while self._lock is held.
    def _remove_connection_locked(self, websocket: WebSocket) -> uuid.UUID | None:
        """Remove a single connection.  Caller MUST hold ``self._lock``."""
        self.rate_limiters.pop(websocket, None)
        user_id = self.connection_users.pop(websocket, None)
        if user_id is not None and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self._last_presence_sent_at.pop(user_id, None)
        return user_id

    async def connect(
        self,
        websocket: WebSocket,
        user_id: uuid.UUID,
        *,
        subprotocol: str | None = None,
    ) -> bool:
        """Accept a WebSocket connection and register it for the user.

        Returns True when accepted, False when rejected (per-user limit reached).
        The limit check and registration happen inside a single lock acquisition
        to prevent races (OZ-2: audit 2026-02-26).
        """
        # TD-14-02 (audit Wave 14): Use explicit Settings fields instead of
        # getattr(..., default).  The fields are declared in base.py with
        # their defaults so IDE autocompletion and type-checking work.
        limit = settings.ws_max_connections_per_user
        async with self._get_lock():
            current_conns = self.active_connections.get(user_id, set())
            if len(current_conns) >= limit:
                await websocket.close(code=1008, reason="Connection limit exceeded")
                logger.warning(
                    "ws_connection_limit_reached",
                    user_id=str(user_id),
                    current=len(current_conns),
                    limit=limit,
                )
                return False

            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            self.active_connections.setdefault(user_id, set()).add(websocket)
            self.connection_users[websocket] = user_id

            rate = settings.ws_message_rate
            burst = settings.ws_message_burst
            self.rate_limiters[websocket] = WebSocketRateLimiter(rate, burst)

        logger.info("ws_connected", user_id=str(user_id))
        return True

    async def disconnect(self, websocket: WebSocket) -> uuid.UUID | None:
        """Remove a WebSocket connection and return the user_id if found.

        WS-1: Lock ensures disconnect() and connect() are mutually exclusive to
        prevent the per-user cap from being bypassed by a race condition.
        """
        async with self._get_lock():
            user_id = self._remove_connection_locked(websocket)
            if user_id is not None:
                logger.info("ws_disconnected", user_id=str(user_id))
            return user_id

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        """Consume a rate-limit token. Returns True if allowed, False if exceeded."""
        limiter = self.rate_limiters.get(websocket)
        if limiter is None:
            return True
        return limiter.consume()

    def is_online(self, user_id: uuid.UUID) -> bool:
        """Return True if the user has at least one active connection."""
        return (
            user_id in self.active_connections
            and len(self.active_connections[user_id]) > 0
        )

    async def send_to_user(self, user_id: uuid.UUID, message: dict[str, Any]) -> int:
        """Send a message to all connections of a user. Returns successful send count.

        PERF-14-01 (audit Wave 14): Reduced from two lock acquisitions to one
        in the common path (no dead connections).  Copy-on-read snapshot avoids
        holding the lock during async I/O.
        """
        async with self._get_lock():
            connections_snapshot = list(self.active_connections.get(user_id, set()))

        if not connections_snapshot:
            return 0

        sent = 0
        dead_connections: list[WebSocket] = []

        for connection in connections_snapshot:
            try:
                await connection.send_json(message)
                sent += 1
            # TD-14-06 (audit Wave 14): Narrow exception types.  The previous
            # bare ``except Exception`` swallowed unexpected errors silently.
            except (WebSocketDisconnect, RuntimeError, ConnectionError) as exc:
                logger.warning("ws_send_failed", user_id=str(user_id), err=str(exc))
                dead_connections.append(connection)

        # PERF-5: Batch dead-connection cleanup inside a single lock acquisition.
        if dead_connections:
            async with self._get_lock():
                for conn in dead_connections:
                    uid = self._remove_connection_locked(conn)
                    if uid is not None:
                        logger.info("ws_batch_disconnected", user_id=str(uid))

        return sent

    async def _get_chat_participants_cached(
        self, chat_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Fetch participant IDs for a chat, using Redis cache if available.

        PERF-14-03 (audit Wave 14): Per-chat asyncio.Lock implements a
        single-flight pattern — when the cache TTL expires, only one concurrent
        caller hits the DB; the others wait and then read the freshly cached
        result.

        RZ-14-05 (audit Wave 14): Uses the injected ``_session_factory`` rather
        than the module-level ``async_session`` import, aligning with Dishka DI
        conventions and enabling test-double injection.
        """
        cache = get_cache()
        cache_key = versioned_key(f"chat:{chat_id}:participants")

        if cache.enabled:
            entry = await cache.get(cache_key)
            if entry:
                return [uuid.UUID(uid) for uid in entry.payload]

        # Single-flight: only one DB query per chat_id at a time.
        # RZ-14-04 / W203 SW8: bind a LOCAL strong ref to the Lock BEFORE storing
        # it in the WeakValueDictionary. `weak[key] = asyncio.Lock()` stores only a
        # weak ref to a temporary that has no strong reference, so CPython
        # refcounting reclaims it at end-of-statement → the read-back KeyErrors
        # deterministically (surfaced by the REST mark_read broadcast — the first
        # end-to-end caller through this branch with the cache disabled). The local
        # `lock` keeps the object alive across the `async with lock:` below.
        lock = self._participant_locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._participant_locks[chat_id] = lock
        async with lock:
            # Double-check after acquiring lock — another coroutine may have
            # already populated the cache while we were waiting.
            if cache.enabled:
                entry = await cache.get(cache_key)
                if entry:
                    return [uuid.UUID(uid) for uid in entry.payload]

            factory = self._session_factory
            if factory is None:
                from app.core.database import async_session

                factory = async_session

            async with factory() as session:
                repo = ChatRepository(session)
                participants = await repo.get_participants(chat_id)

            if cache.enabled:
                await cache.set(cache_key, participants, ttl=3600)

        return participants

    async def broadcast_to_chat(
        self,
        chat_id: uuid.UUID,
        message: dict[str, Any],
        exclude_user_id: uuid.UUID | None = None,
    ) -> int:
        """Broadcast a message to all participants of a chat. Returns total sends.

        PERF-1 (audit 2026-02-26): Fan-out via asyncio.gather so latency scales
        with the slowest single send rather than O(N × send_time).
        """
        participant_ids = await self._get_chat_participants_cached(chat_id)
        targets = [
            p_id
            for p_id in participant_ids
            if exclude_user_id is None or p_id != exclude_user_id
        ]

        room_sem = await _get_room_semaphore(str(chat_id))

        async def _throttled_send(uid: uuid.UUID) -> int:
            async with room_sem:
                return await self.send_to_user(uid, message)

        results = await asyncio.gather(
            *(_throttled_send(p_id) for p_id in targets),
            return_exceptions=True,
        )
        return sum(r for r in results if isinstance(r, int))

    def _should_broadcast_presence(
        self, user_id: uuid.UUID, now: datetime, *, force: bool
    ) -> bool:
        min_interval = max(settings.presence_ping_min_interval_seconds, 0)
        if force or min_interval <= 0:
            return True
        last_sent = self._last_presence_sent_at.get(user_id)
        if last_sent is None:
            return True
        return (now - last_sent).total_seconds() >= min_interval

    async def broadcast_presence(
        self,
        user_id: uuid.UUID,
        active: bool,
        last_seen: datetime | None,
        *,
        source: str,
        force: bool = False,
        publish: bool = True,
    ) -> int:
        """Broadcast presence status to relevant chat participants."""
        from app.api.ws.presence import _get_presence_audience, presence_pubsub

        now = datetime.now(UTC)
        state = "active" if active else "inactive"
        if not self._should_broadcast_presence(user_id, now, force=force):
            record_presence_throttled(state, source)
            return 0
        self._last_presence_sent_at[user_id] = now
        record_presence_event(state, source)

        payload: dict[str, Any] = {
            "type": "presence",
            "user_id": user_id,
            "active": active,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }

        if publish:
            await presence_pubsub.publish(payload)

        audience = await _get_presence_audience(user_id)
        if not audience:
            return 0

        async def _throttled_presence_send(uid: uuid.UUID) -> int:
            async with _get_presence_semaphore():
                return await self.send_to_user(uid, payload)

        results = await asyncio.gather(
            *(_throttled_presence_send(uid) for uid in audience),
            return_exceptions=True,
        )
        return sum(r for r in results if isinstance(r, int))

    def get_online_users(self) -> list[uuid.UUID]:
        """Return all currently online user IDs."""
        return list(self.active_connections.keys())


# Module-level singleton — assigned by lifespan before the first request.
# FastAPI route handlers should prefer get_connection_manager() so mocks
# can be injected in tests.
manager: ConnectionManager = ConnectionManager()


def get_connection_manager(request: Request) -> ConnectionManager:
    """FastAPI dependency — returns the app-state ConnectionManager."""
    cm = getattr(request.app.state, "connection_manager", None)
    if cm is None:
        return manager
    return cast(ConnectionManager, cm)
