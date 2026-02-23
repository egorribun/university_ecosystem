"""
WebSocket endpoint for real-time chat messaging.

This module provides WebSocket connections for:
- Real-time message delivery
- Typing indicators
- Read receipts
- Online status
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.core import metrics
from app.core.config import settings
from app.core.database import async_session
from app.core.feature_flags import feature_flags
from app.core.metrics import record_presence_event, record_presence_throttled
from app.deps.cache import get_cache, versioned_key
from app.models.chat import Message, chat_participants
from app.models.enums import UserRole
from app.models.models import ActiveSession, User
from app.schemas.chat import ChatParticipant, PresenceStatus
from app.services.audit_service import SecurityEvent, audit_service
from app.utils.logging import redact_sensitive_mapping

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


PRESENCE_SOURCE_CONNECT = "connect"
PRESENCE_SOURCE_DISCONNECT = "disconnect"
PRESENCE_SOURCE_PING = "ping"
PRESENCE_SOURCE_PUBSUB = "pubsub"

_PRESENCE_INSTANCE_ID = uuid.uuid4().hex


async def _get_presence_audience(user_id: uuid.UUID) -> set[uuid.UUID]:
    """Resolve user IDs that should receive presence updates for user_id."""
    cache = get_cache()
    cache_key = versioned_key(f"user:{user_id}:presence_audience")

    if cache.enabled:
        entry = await cache.get(cache_key)
        if entry:
            return set(entry.payload)

    async with async_session() as session:
        chat_ids = select(chat_participants.c.chat_id).where(
            chat_participants.c.user_id == user_id
        )
        result = await session.execute(
            select(chat_participants.c.user_id)
            .distinct()
            .where(chat_participants.c.chat_id.in_(chat_ids))
        )
        audience = {row[0] for row in result.all()}

    audience.discard(user_id)

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


async def _get_online_users_for_user(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Return online user IDs limited to the current user's chat participants."""
    audience = await _get_presence_audience(user_id)
    return [target_id for target_id in audience if manager.is_online(target_id)]


def _get_websocket_audit_context(websocket: WebSocket) -> dict[str, Any]:
    client = websocket.client
    return {
        "ws_path": websocket.url.path,
        "ws_client": client.host if client else None,
    }


class PresencePubSub:
    """Optional Redis pub/sub bridge for presence events."""

    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._pubsub_task: asyncio.Task | None = None

    async def initialize(self, redis: Redis | None = None) -> None:
        if self._redis or not settings.presence_pubsub_enabled:
            return
        if redis is not None:
            self._redis = redis
        elif settings.cache_redis_url:
            self._redis = Redis.from_url(
                settings.cache_redis_url, decode_responses=True
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
            await ps.unsubscribe(settings.presence_pubsub_channel)
            await ps.close()
        except Exception as exc:
            logger.error("Presence Pub/Sub listener error: %s", exc)


presence_pubsub = PresencePubSub()


class ConnectionManager:
    """Manages WebSocket connections for all users."""

    # Maximum concurrent WebSocket connections a single user may hold.
    # Prevents memory exhaustion from DoS via connection flooding.
    # Override via settings.ws_max_connections_per_user if needed.
    MAX_CONNECTIONS_PER_USER: int = 5

    def __init__(self) -> None:
        # user_id -> set of WebSocket connections (user can have multiple tabs/devices)
        self.active_connections: dict[uuid.UUID, set[WebSocket]] = {}
        # websocket -> user_id (for reverse lookup on disconnect)
        self.connection_users: dict[WebSocket, uuid.UUID] = {}
        self._last_presence_sent_at: dict[uuid.UUID, datetime] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: uuid.UUID,
        *,
        subprotocol: str | None = None,
    ) -> bool:
        """Accept a WebSocket connection and register it for the user.

        Returns True when the connection was accepted, False when it was rejected
        because the per-user connection limit has been reached.
        """
        current_conns = self.active_connections.get(user_id, set())
        limit = getattr(settings, "ws_max_connections_per_user", self.MAX_CONNECTIONS_PER_USER)
        if len(current_conns) >= limit:
            # Reject BEFORE accepting — the client will receive a proper close frame.
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
        logger.info("WebSocket connected: user_id=%s", user_id)
        return True

    def disconnect(self, websocket: WebSocket) -> uuid.UUID | None:
        """Remove a WebSocket connection and return the user_id if found."""
        user_id = self.connection_users.pop(websocket, None)
        if user_id is not None and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Clean up presence throttle state only when the last connection closes.
                # If the user has multiple tabs open, keep the throttle to avoid presence spam.
                self._last_presence_sent_at.pop(user_id, None)
            logger.info("WebSocket disconnected: user_id=%s", user_id)
        return user_id

    def is_online(self, user_id: uuid.UUID) -> bool:
        """Check if a user has any active connections."""
        return (
            user_id in self.active_connections
            and len(self.active_connections[user_id]) > 0
        )

    async def send_to_user(self, user_id: uuid.UUID, message: dict[str, Any]) -> int:
        """
        Send a message to all connections of a user.
        Returns number of successful sends.
        """
        if user_id not in self.active_connections:
            return 0

        sent = 0
        dead_connections: list[WebSocket] = []

        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
                sent += 1
            except Exception as e:
                logger.warning("Failed to send to user %s: %s", user_id, e)
                dead_connections.append(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)

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
            stmt = select(chat_participants.c.user_id).where(
                chat_participants.c.chat_id == chat_id
            )
            result = await session.execute(stmt)
            participants = [row[0] for row in result.all()]

        if cache.enabled:
            await cache.set(cache_key, participants, ttl=3600)

        return participants

    async def broadcast_to_chat(
        self,
        chat_id: uuid.UUID,
        message: dict[str, Any],
        exclude_user_id: uuid.UUID | None = None,
    ) -> int:
        """Broadcast a message to all participants of a chat. Returns total sends."""
        total_sent = 0
        participant_ids = await self._get_chat_participants_cached(chat_id)

        for p_id in participant_ids:
            if exclude_user_id and p_id == exclude_user_id:
                continue
            total_sent += await self.send_to_user(p_id, message)

        return total_sent

    def _should_broadcast_presence(
        self, user_id: uuid.UUID, now: datetime, *, force: bool
    ) -> bool:
        min_interval = max(settings.presence_ping_min_interval_seconds, 0)
        if force or min_interval <= 0:
            return True
        last_sent = self._last_presence_sent_at.get(user_id)
        if last_sent is None:
            return True
        elapsed = (now - last_sent).total_seconds()
        return elapsed >= min_interval

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
        now = datetime.now(UTC)
        state = "active" if active else "inactive"
        if not self._should_broadcast_presence(user_id, now, force=force):
            record_presence_throttled(state, source)
            return 0
        self._last_presence_sent_at[user_id] = now
        record_presence_event(state, source)

        payload = {
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

        # Fan-out to all audience members concurrently instead of sequentially.
        # asyncio.gather preserves order and collects exceptions without crashing.
        results = await asyncio.gather(
            *(self.send_to_user(uid, payload) for uid in audience),
            return_exceptions=True,
        )
        total_sent = sum(r for r in results if isinstance(r, int))
        return total_sent

    def get_online_users(self) -> list[uuid.UUID]:
        """Get list of all online user IDs."""
        return list(self.active_connections.keys())


# Module-level reference — assigned by ``lifespan`` (app/core/lifespan.py) before
# the first request is served.  Non-request contexts (pubsub handlers, background
# tasks) use this directly.  FastAPI route handlers should prefer the
# ``get_connection_manager`` dependency so mocks can be injected in tests.
manager: ConnectionManager = ConnectionManager()  # default replaced at startup


def get_connection_manager(request: Request) -> ConnectionManager:  # type: ignore[name-defined]
    """FastAPI dependency — returns the app-state ConnectionManager.

    Usage::

        @router.get("/example")
        async def example(cm: Annotated[ConnectionManager, Depends(get_connection_manager)]):
            ...
    """
    return request.app.state.connection_manager


async def _handle_presence_pubsub(payload: dict[str, Any]) -> None:
    user_id = payload.get("user_id")
    if user_id is None:
        return
    active = bool(payload.get("active"))
    last_seen_raw = payload.get("last_seen")
    last_seen = None
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(str(last_seen_raw))
        except ValueError:
            logger.warning("Invalid last_seen value in presence payload")
    await manager.broadcast_presence(
        uuid.UUID(str(user_id)),
        active,
        last_seen,
        source=PRESENCE_SOURCE_PUBSUB,
        force=True,
        publish=False,
    )


async def start_presence_pubsub() -> None:
    await presence_pubsub.initialize()


async def stop_presence_pubsub() -> None:
    await presence_pubsub.shutdown()


async def get_user_from_token(token: str) -> tuple[User | None, str | None]:
    """Validate JWT token and return the user and session identifier."""
    from app.auth.security import decode_token

    try:
        payload = decode_token(token)
        if not payload:
            return None, None

        user_id = payload.get("sub")
        session_jti = payload.get("jti")
        if not user_id:
            return None, None

        async with async_session() as session:
            user = await session.get(User, uuid.UUID(user_id))
            if not user or not user.is_active:
                return None, None

            if not session_jti:
                return None, None

            result = await session.execute(
                select(ActiveSession).where(ActiveSession.jti == session_jti)
            )
            active_session = result.scalars().first()
            if not active_session or active_session.user_id != user.id:
                return None, None

            expires_at = active_session.expires_at
            if expires_at is None:
                return None, None  # type: ignore[unreachable]

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            if expires_at <= datetime.now(UTC):
                return None, None

            if active_session.revoked_at is not None:
                return None, None
            return user, session_jti
    except Exception as e:
        logger.warning("Token validation failed: %s", e)
        return None, None


async def get_user_from_cookie(cookie_value: str) -> tuple[User | None, str | None]:
    """Validate session cookie and return the user."""

    try:
        # The cookie contains the JWT token directly
        return await get_user_from_token(cookie_value)
    except Exception as e:
        logger.warning("Cookie validation failed: %s", e)
        return None, None


def _extract_bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    parts = header_value.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def _extract_token_from_subprotocol(header_value: str | None) -> str | None:
    if not header_value:
        return None
    protocols = [
        protocol.strip() for protocol in header_value.split(",") if protocol.strip()
    ]
    for index, protocol in enumerate(protocols):
        if protocol.lower() in {"access_token", "bearer", "authorization"}:
            if index + 1 < len(protocols):
                return protocols[index + 1]
    return None


def _select_subprotocol(header_value: str | None) -> str | None:
    if not header_value:
        return None
    protocols = [
        protocol.strip() for protocol in header_value.split(",") if protocol.strip()
    ]
    for candidate in protocols:
        if candidate.lower() in {"access_token", "bearer"}:
            return candidate
    return None


async def _update_last_seen(session_jti: str | None) -> datetime:
    """Persist last_seen_at for a session and return the timestamp used."""

    now = datetime.now(UTC)
    if not session_jti:
        return now

    async with async_session() as session:
        result = await session.execute(
            select(ActiveSession).where(ActiveSession.jti == session_jti)
        )
        active_session = result.scalars().first()
        if active_session:
            active_session.last_seen_at = now
            await session.commit()

    return now


async def build_presence_map(
    user_ids: Iterable[uuid.UUID], session: AsyncSession | None = None
) -> dict[uuid.UUID, PresenceStatus]:
    """Return presence info for a set of users."""

    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}

    if session:
        # Use provided session
        result = await session.execute(
            select(ActiveSession.user_id, func.max(ActiveSession.last_seen_at))
            .where(ActiveSession.user_id.in_(ids))
            .group_by(ActiveSession.user_id)
        )
        last_seen_map = {row[0]: row[1] for row in result.all()}
    else:
        # Create new session
        async with async_session() as new_session:
            result = await new_session.execute(
                select(ActiveSession.user_id, func.max(ActiveSession.last_seen_at))
                .where(ActiveSession.user_id.in_(ids))
                .group_by(ActiveSession.user_id)
            )
            last_seen_map = {row[0]: row[1] for row in result.all()}

    presence: dict[uuid.UUID, PresenceStatus] = {}
    for uid in ids:
        presence[uid] = PresenceStatus(
            active=manager.is_online(uid),
            last_seen_at=last_seen_map.get(uid),
        )
    return presence


def serialize_message(
    message: Message, presence: dict[uuid.UUID, PresenceStatus] | None = None
) -> dict[str, Any]:
    """Serialize a Message object for WebSocket transmission."""
    sender_data = None
    if message.sender:
        sender_data = ChatParticipant.model_validate(message.sender).model_dump()

    sender_presence = None
    if presence and message.sender_id in presence:
        status = presence[message.sender_id]
        sender_presence = {
            "active": status.active,
            "last_seen_at": (
                status.last_seen_at.isoformat() if status.last_seen_at else None
            ),
        }

    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender_id": message.sender_id,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "read_status": message.read_status,
        "sender": sender_data,
        "sender_presence": sender_presence,
        "attachments": [
            {
                "id": att.id,
                "url": att.url,
                "file_type": att.file_type,
                "filename": att.filename,
                "size": att.size,
            }
            for att in (message.attachments or [])
        ],
    }


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.

    Authentication:
    - Send JWT in `Sec-WebSocket-Protocol` (e.g. `access_token, <JWT>`), OR
    - Send `Authorization: Bearer <JWT>` header, OR
    - Use cookie-based auth (access_token cookie)
    - Query param `token` can be enabled temporarily via
      feature flag `websocket_query_param_compat`

    Message types (from client):
    - {"type": "ping"} - Keep-alive ping
    - {"type": "typing", "chat_id": "..."} - Typing indicator
    - {"type": "read", "chat_id": "...", "message_id": "..."} - Mark message as read

    Message types (to client):
    - {"type": "pong"} - Response to ping
    - {"type": "new_message", "chat_id": "...", "message": {...}} - New message received
    - {"type": "typing", "chat_id": "...", "user_id": ...} - Someone is typing
    - {"type": "read", "chat_id": "...", "message_id": "...", "user_id": ...}
      - Message read
    - {"type": "presence", "user_id": ..., "active": true/false, "last_seen": "..."}
      - Participant presence updates
    - {"type": "error", "message": "..."} - Error message
    """
    user = None
    session_jti = None

    # Debug: log incoming connection info
    logger.info(
        "WebSocket connection attempt - cookies: %s",
        redact_sensitive_mapping(websocket.cookies, allowlist=("session", "csrftoken")),
    )
    logger.info(
        "WebSocket connection attempt - query params: %s",
        redact_sensitive_mapping(
            dict(websocket.query_params), allowlist=("client", "version")
        ),
    )

    auth_header = websocket.headers.get("authorization")
    protocol_header = websocket.headers.get("sec-websocket-protocol")
    header_token = _extract_bearer_token(auth_header)
    protocol_token = _extract_token_from_subprotocol(protocol_header)
    selected_subprotocol = _select_subprotocol(protocol_header)

    if header_token or protocol_token:
        logger.info(
            "Attempting WebSocket token auth from headers (auth=%s, protocol=%s)",
            bool(header_token),
            bool(protocol_token),
        )
        token_str = str(header_token or protocol_token)
        user, session_jti = await get_user_from_token(token_str)
        if user:
            logger.info("Token auth successful: user_id=%s", user.id)
        else:
            logger.warning("Token auth failed: invalid token")

    # Fallback to cookie-based auth
    if not user and feature_flags.is_enabled("websocket_query_param_compat"):
        token = websocket.query_params.get("token")
        if token:
            logger.info("Attempting token auth from query params (compat mode)")
            user, session_jti = await get_user_from_token(token)
            if user:
                logger.info("Token auth successful: user_id=%s", user.id)
            else:
                logger.warning("Token auth failed: invalid token")

    if not user:
        access_token = websocket.cookies.get("access_token_v2")
        logger.info(
            "Attempting cookie auth, access_token present: %s", bool(access_token)
        )
        if access_token:
            user, session_jti = await get_user_from_cookie(access_token)
            if user:
                logger.info("Cookie auth successful: user_id=%s", user.id)
            else:
                logger.warning("Cookie auth failed: invalid cookie")

    if not user:
        logger.warning("WebSocket auth failed - no valid credentials")
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Connect and register — may reject if per-user limit is reached
    accepted = await manager.connect(websocket, user.id, subprotocol=selected_subprotocol)
    if not accepted:
        return  # close frame already sent inside connect()
    metrics.inc_ws_connections(path="/ws/chat")
    last_seen = await _update_last_seen(session_jti)
    await manager.broadcast_presence(
        user.id,
        True,
        last_seen,
        source=PRESENCE_SOURCE_CONNECT,
        force=True,
    )

    try:
        # Send initial online status to user's contacts
        # (In a full implementation, you'd notify friends/chat participants)

        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                last_seen = await _update_last_seen(session_jti)
                await websocket.send_json({"type": "pong"})
                await manager.broadcast_presence(
                    user.id,
                    True,
                    last_seen,
                    source=PRESENCE_SOURCE_PING,
                )

            elif msg_type == "typing":
                chat_id = data.get("chat_id")
                if chat_id:
                    # Validate user is participant to prevent IDOR
                    try:
                        chat_uuid = (
                            uuid.UUID(chat_id) if isinstance(chat_id, str) else chat_id
                        )
                        participants = await manager._get_chat_participants_cached(
                            chat_uuid
                        )
                        if user.id not in participants:
                            logger.warning(
                                f"Access denied: User {user.id} tried to send typing "
                                f"indicator to chat {chat_id} without being a participant"
                            )
                            await websocket.send_json(
                                {"type": "error", "message": "Access denied"}
                            )
                            continue
                    except ValueError:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid chat_id format"}
                        )
                        continue

                    # Broadcast typing indicator to other participants
                    await manager.broadcast_to_chat(
                        chat_uuid,
                        {
                            "type": "typing",
                            "chat_id": str(chat_uuid),
                            "user_id": str(user.id),
                            "user_name": user.full_name or user.email,
                        },
                        exclude_user_id=user.id,
                    )

            elif msg_type == "read":
                chat_id = data.get("chat_id")
                message_id = data.get("message_id")
                if chat_id and message_id:
                    # Update message read status in DB
                    async with async_session() as session:
                        # Verify that the user is a participant of the chat (Fix IDOR)
                        is_participant_stmt = select(chat_participants).where(
                            chat_participants.c.chat_id == chat_id,
                            chat_participants.c.user_id == user.id,
                        )
                        is_participant = (
                            await session.execute(is_participant_stmt)
                        ).first()
                        if not is_participant:
                            logger.warning(
                                f"User {user.id} tried to mark message {message_id} "
                                f"as read in chat {chat_id} without being a participant"
                            )
                            await websocket.send_json(
                                {"type": "error", "message": "Access denied"}
                            )
                            continue

                        msg = await session.get(Message, message_id)
                        if msg and msg.chat_id == chat_id and msg.sender_id != user.id:
                            msg.read_status = True
                            await session.commit()

                            # Notify sender that message was read
                            await manager.send_to_user(
                                msg.sender_id,
                                {
                                    "type": "read",
                                    "chat_id": chat_id,
                                    "message_id": message_id,
                                    "user_id": user.id,
                                },
                            )

            elif msg_type == "get_online":
                if user.role != UserRole.ADMIN.value:
                    audit_service.log(
                        SecurityEvent.ACCESS_DENIED,
                        user_id=user.id,
                        reason="admin_required",
                        action="presence.get_online",
                        **_get_websocket_audit_context(websocket),
                    )
                    await websocket.send_json(
                        {"type": "error", "message": "Access denied"}
                    )
                    continue

                online = await _get_online_users_for_user(user.id)
                audit_service.log(
                    "presence.online_list",
                    user_id=user.id,
                    action="presence.get_online",
                    result_count=len(online),
                    scope="chat_participants",
                    **_get_websocket_audit_context(websocket),
                )
                await websocket.send_json({"type": "online_list", "users": online})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(
            user.id,
            False,
            last_seen,
            source=PRESENCE_SOURCE_DISCONNECT,
            force=True,
        )
        logger.info("WebSocket disconnected for user %s", user.id)
    except Exception as e:
        logger.error("WebSocket error for user %s: %s", user.id, e)
        manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(
            user.id,
            False,
            last_seen,
            source=PRESENCE_SOURCE_DISCONNECT,
            force=True,
        )
    finally:
        metrics.dec_ws_connections(path="/ws/chat")
        logger.info("WebSocket cleanup for user %s", user.id)


async def notify_new_message(
    message: Message, exclude_user_id: uuid.UUID | None = None
) -> int:
    """
    Notify chat participants about a new message via WebSocket.
    Call this from the chat API after saving a message.

    Returns the number of successful notifications sent.
    """
    presence = await build_presence_map([message.sender_id])
    metrics.record_chat_message(channel=str(message.chat_id))
    return await manager.broadcast_to_chat(
        message.chat_id,
        {
            "type": "new_message",
            "chat_id": message.chat_id,
            "message": serialize_message(message, presence),
        },
        exclude_user_id=exclude_user_id,
    )


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager
