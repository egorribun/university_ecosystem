"""
WebSocket endpoint for real-time chat messaging.

This module provides WebSocket connections for:
- Real-time message delivery
- Typing indicators
- Read receipts
- Online status
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.models.chat import Chat, Message
from app.models.models import ActiveSession, User
from app.schemas.chat import ChatParticipant, PresenceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for all users."""

    def __init__(self):
        # user_id -> set of WebSocket connections (user can have multiple tabs/devices)
        self.active_connections: dict[int, set[WebSocket]] = {}
        # websocket -> user_id (for reverse lookup on disconnect)
        self.connection_users: dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Accept a WebSocket connection and register it for the user."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        self.connection_users[websocket] = user_id
        logger.info(f"WebSocket connected: user_id={user_id}")

    def disconnect(self, websocket: WebSocket) -> int | None:
        """Remove a WebSocket connection and return the user_id if found."""
        user_id = self.connection_users.pop(websocket, None)
        if user_id is not None and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"WebSocket disconnected: user_id={user_id}")
        return user_id

    def is_online(self, user_id: int) -> bool:
        """Check if a user has any active connections."""
        return (
            user_id in self.active_connections
            and len(self.active_connections[user_id]) > 0
        )

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> int:
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
                logger.warning(f"Failed to send to user {user_id}: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)

        return sent

    async def broadcast_to_chat(
        self, chat_id: str, message: dict[str, Any], exclude_user_id: int | None = None
    ) -> int:
        """Broadcast a message to all participants of a chat. Returns total sends."""
        total_sent = 0
        async with async_session() as session:
            chat = await session.get(
                Chat, chat_id, options=[selectinload(Chat.participants)]
            )
            if chat:
                for participant in chat.participants:
                    if exclude_user_id and participant.id == exclude_user_id:
                        continue
                    total_sent += await self.send_to_user(participant.id, message)
        return total_sent

    async def broadcast_presence(
        self, user_id: int, active: bool, last_seen: datetime | None
    ) -> int:
        """Broadcast presence status to all connected users."""

        payload = {
            "type": "presence",
            "user_id": user_id,
            "active": active,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }

        total_sent = 0
        for target_user in list(self.active_connections.keys()):
            total_sent += await self.send_to_user(target_user, payload)
        return total_sent

    def get_online_users(self) -> list[int]:
        """Get list of all online user IDs."""
        return list(self.active_connections.keys())


# Global connection manager instance
manager = ConnectionManager()


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
            user = await session.get(User, int(user_id))
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
                return None, None

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            if expires_at <= datetime.now(UTC):
                return None, None

            if active_session.revoked_at is not None:
                return None, None

            return user, session_jti
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None, None


async def get_user_from_cookie(cookie_value: str) -> tuple[User | None, str | None]:
    """Validate session cookie and return the user."""

    try:
        # The cookie contains the JWT token directly
        return await get_user_from_token(cookie_value)
    except Exception as e:
        logger.warning(f"Cookie validation failed: {e}")
        return None, None


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


async def build_presence_map(user_ids: Iterable[int]) -> dict[int, PresenceStatus]:
    """Return presence info for a set of users."""

    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}

    async with async_session() as session:
        result = await session.execute(
            select(ActiveSession.user_id, func.max(ActiveSession.last_seen_at))
            .where(ActiveSession.user_id.in_(ids))
            .group_by(ActiveSession.user_id)
        )
        last_seen_map = {row[0]: row[1] for row in result.all()}

    presence: dict[int, PresenceStatus] = {}
    for uid in ids:
        presence[uid] = PresenceStatus(
            active=manager.is_online(uid),
            last_seen_at=last_seen_map.get(uid),
        )
    return presence


def serialize_message(
    message: Message, presence: dict[int, PresenceStatus] | None = None
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
    - Pass JWT token as query parameter `token`, OR
    - Use cookie-based auth (access_token cookie)

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
        f"WebSocket connection attempt - cookies: {list(websocket.cookies.keys())}"
    )
    logger.info(
        f"WebSocket connection attempt - query params: {dict(websocket.query_params)}"
    )

    # Try token from query params first
    token = websocket.query_params.get("token")
    if token:
        logger.info("Attempting token auth from query params")
        user, session_jti = await get_user_from_token(token)
        if user:
            logger.info(f"Token auth successful: user_id={user.id}")
        else:
            logger.warning("Token auth failed: invalid token")

    # Fallback to cookie-based auth
    if not user:
        access_token = websocket.cookies.get("access_token")
        logger.info(
            f"Attempting cookie auth, access_token present: {bool(access_token)}"
        )
        if access_token:
            user, session_jti = await get_user_from_cookie(access_token)
            if user:
                logger.info(f"Cookie auth successful: user_id={user.id}")
            else:
                logger.warning("Cookie auth failed: invalid cookie")

    if not user:
        logger.warning("WebSocket auth failed - no valid credentials")
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Connect and register
    await manager.connect(websocket, user.id)
    last_seen = await _update_last_seen(session_jti)
    await manager.broadcast_presence(user.id, True, last_seen)

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
                await manager.broadcast_presence(user.id, True, last_seen)

            elif msg_type == "typing":
                chat_id = data.get("chat_id")
                if chat_id:
                    # Broadcast typing indicator to other participants
                    await manager.broadcast_to_chat(
                        chat_id,
                        {
                            "type": "typing",
                            "chat_id": chat_id,
                            "user_id": user.id,
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
                # Return list of online users (for debugging/admin)
                online = manager.get_online_users()
                await websocket.send_json({"type": "online_list", "users": online})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(user.id, False, last_seen)
        logger.info(f"WebSocket disconnected for user {user.id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
        manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(user.id, False, last_seen)


async def notify_new_message(
    message: Message, exclude_user_id: int | None = None
) -> int:
    """
    Notify chat participants about a new message via WebSocket.
    Call this from the chat API after saving a message.

    Returns the number of successful notifications sent.
    """
    presence = await build_presence_map([message.sender_id])
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
