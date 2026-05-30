"""WebSocket message serializers and presence map builder.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: convert domain objects to WebSocket-wire format.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models.chat import Message
from app.schemas.chat import ChatParticipant, PresenceStatus


def serialize_message(
    message: Message,
    presence: dict[uuid.UUID, PresenceStatus] | None = None,
) -> dict[str, Any]:
    """Serialize a Message ORM object for WebSocket transmission."""
    sender_data = None
    if getattr(message, "sender", None):
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
        # Wave 203 SW3 — read-receipt timestamp (ISO 8601 or None). Surfaces in
        # the new_message broadcast + the chat-level read broadcast (SW4).
        "read_at": message.read_at.isoformat() if message.read_at else None,
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
