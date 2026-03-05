"""WebSocket connection management — ConnectionManager and rate limiter.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: connection lifecycle and per-connection rate limiting.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import Request, WebSocket

from app.core.config import settings
from app.core.database import async_session
from app.core.metrics import record_presence_event, record_presence_throttled
from app.deps.cache import get_cache, versioned_key
from app.repositories.chat_repository import ChatRepository

logger = logging.getLogger(__name__)


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


class ConnectionManager:
    """Manages WebSocket connections for all users."""

    MAX_CONNECTIONS_PER_USER: int = 5

    def __init__(self) -> None:
        self.active_connections: dict[uuid.UUID, set[WebSocket]] = {}
        self.connection_users: dict[WebSocket, uuid.UUID] = {}
        self.rate_limiters: dict[WebSocket, WebSocketRateLimiter] = {}
        self._last_presence_sent_at: dict[uuid.UUID, datetime] = {}
        # PERF-4 (audit 2026-03-05): Eagerly initialised asyncio.Lock — always safe
        # because ConnectionManager is instantiated inside lifespan startup.
        self._lock: asyncio.Lock = asyncio.Lock()

    def _get_lock(self) -> asyncio.Lock:
        return self._lock

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
        limit = getattr(
            settings, "ws_max_connections_per_user", self.MAX_CONNECTIONS_PER_USER
        )
        async with self._get_lock():
            current_conns = self.active_connections.get(user_id, set())
            if len(current_conns) >= limit:
                await websocket.close(code=1008, reason="Connection limit exceeded")
                logger.warning(
                    "WS connection limit reached for user %s (%d/%d) — rejected",
                    user_id,
                    len(current_conns),
                    limit,
                )
                return False

            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            self.active_connections.setdefault(user_id, set()).add(websocket)
            self.connection_users[websocket] = user_id

            rate = getattr(settings, "ws_message_rate", 5.0)
            burst = getattr(settings, "ws_message_burst", 10.0)
            self.rate_limiters[websocket] = WebSocketRateLimiter(rate, burst)

        logger.info("WebSocket connected: user_id=%s", user_id)
        return True

    async def disconnect(self, websocket: WebSocket) -> uuid.UUID | None:
        """Remove a WebSocket connection and return the user_id if found.

        WS-1: Lock ensures disconnect() and connect() are mutually exclusive to
        prevent the per-user cap from being bypassed by a race condition.
        """
        async with self._get_lock():
            self.rate_limiters.pop(websocket, None)
            user_id = self.connection_users.pop(websocket, None)
            if user_id is not None and user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    self._last_presence_sent_at.pop(user_id, None)
                logger.info("WebSocket disconnected: user_id=%s", user_id)
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
        """Send a message to all connections of a user. Returns successful send count."""
        if user_id not in self.active_connections:
            return 0

        sent = 0
        dead_connections: list[WebSocket] = []

        async with self._get_lock():
            connections_snapshot = set(self.active_connections.get(user_id, set()))

        for connection in connections_snapshot:
            try:
                await connection.send_json(message)
                sent += 1
            except Exception as exc:
                logger.warning("Failed to send to user %s: %s", user_id, exc)
                dead_connections.append(connection)

        # PERF-5: Batch dead-connection cleanup inside a single lock acquisition.
        if dead_connections:
            async with self._get_lock():
                for conn in dead_connections:
                    self.rate_limiters.pop(conn, None)
                    uid = self.connection_users.pop(conn, None)
                    if uid is not None and uid in self.active_connections:
                        self.active_connections[uid].discard(conn)
                        if not self.active_connections[uid]:
                            del self.active_connections[uid]
                            self._last_presence_sent_at.pop(uid, None)
                        logger.info("WebSocket batch-disconnected: user_id=%s", uid)

        return sent

    async def _get_chat_participants_cached(
        self, chat_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Fetch participant IDs for a chat, using Redis cache if available."""
        cache = get_cache()
        cache_key = versioned_key(f"chat:{chat_id}:participants")

        if cache.enabled:
            entry = await cache.get(cache_key)
            if entry:
                return [uuid.UUID(uid) for uid in entry.payload]

        async with async_session() as session:
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
        results = await asyncio.gather(
            *(self.send_to_user(p_id, message) for p_id in targets),
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

        results = await asyncio.gather(
            *(self.send_to_user(uid, payload) for uid in audience),
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
