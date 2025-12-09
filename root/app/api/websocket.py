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
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.models.chat import Chat, Message
from app.models.models import User
from app.schemas.chat import ChatParticipant, MessageResponse

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
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> int:
        """Send a message to all connections of a user. Returns number of successful sends."""
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

    def get_online_users(self) -> list[int]:
        """Get list of all online user IDs."""
        return list(self.active_connections.keys())


# Global connection manager instance
manager = ConnectionManager()


async def get_user_from_token(token: str) -> User | None:
    """Validate JWT token and return the user."""
    from app.auth.security import decode_token

    try:
        payload = decode_token(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        async with async_session() as session:
            user = await session.get(User, int(user_id))
            return user if user and user.is_active else None
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None


async def get_user_from_cookie(cookie_value: str) -> User | None:
    """Validate session cookie and return the user."""
    from app.auth.security import decode_token

    try:
        # The cookie contains the JWT token directly
        return await get_user_from_token(cookie_value)
    except Exception as e:
        logger.warning(f"Cookie validation failed: {e}")
        return None


def serialize_message(message: Message) -> dict[str, Any]:
    """Serialize a Message object for WebSocket transmission."""
    sender_data = None
    if message.sender:
        sender_data = ChatParticipant.model_validate(message.sender).model_dump()

    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender_id": message.sender_id,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "read_status": message.read_status,
        "sender": sender_data,
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
    - {"type": "read", "chat_id": "...", "message_id": "...", "user_id": ...} - Message read
    - {"type": "online", "user_id": ..., "status": true/false} - User online status
    - {"type": "error", "message": "..."} - Error message
    """
    user = None
    
    # Try token from query params first
    token = websocket.query_params.get("token")
    if token:
        user = await get_user_from_token(token)
    
    # Fallback to cookie-based auth
    if not user:
        access_token = websocket.cookies.get("access_token")
        if access_token:
            user = await get_user_from_cookie(access_token)
    
    if not user:
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Connect and register
    await manager.connect(websocket, user.id)

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
                await websocket.send_json({"type": "pong"})

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
        logger.info(f"WebSocket disconnected for user {user.id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
        manager.disconnect(websocket)


async def notify_new_message(message: Message, exclude_user_id: int | None = None) -> int:
    """
    Notify chat participants about a new message via WebSocket.
    Call this from the chat API after saving a message.

    Returns the number of successful notifications sent.
    """
    return await manager.broadcast_to_chat(
        message.chat_id,
        {
            "type": "new_message",
            "chat_id": message.chat_id,
            "message": serialize_message(message),
        },
        exclude_user_id=exclude_user_id,
    )


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager
