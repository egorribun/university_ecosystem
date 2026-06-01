"""WebSocket message serializers and presence map builder.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: convert domain objects to WebSocket-wire format.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models.chat import Message
from app.schemas.chat import ChatParticipant, PresenceStatus, ReplyPreview


def serialize_message(
    message: Message,
    presence: dict[uuid.UUID, PresenceStatus] | None = None,
    *,
    replied: Any = None,
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

    # Wave 207 — reply quote preview (None when not a reply). `replied` is the
    # replied-to message (a MessageDTO loaded by handle_message_sent with its
    # sender); ReplyPreview.from_message reuses the REST truncation + sender-name
    # logic. UUIDs stay raw (downstream orjson/json default=str stringifies them,
    # matching id/chat_id/sender_id below); the datetime is isoformat'd inline to
    # match this serializer's style.
    reply_to = None
    if replied is not None:
        preview = ReplyPreview.from_message(replied)
        if preview is not None:
            reply_to = {
                "id": preview.id,
                "sender_id": preview.sender_id,
                "sender_name": preview.sender_name,
                "content": preview.content,
                "deleted_at": (
                    preview.deleted_at.isoformat() if preview.deleted_at else None
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
        # Wave 205 SW4 — edit/soft-delete timestamps; a freshly-sent message carries
        # them as None in the new_message broadcast frame.
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
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
        # Wave 207 — reply quote preview for the recipient's live new_message bubble.
        "reply_to": reply_to,
        # Wave 211 — denormalized "Forwarded from X" label (None = not a forward).
        # A plain scalar column (no preview build, no selectinload — contrast
        # reply_to). The audit-only forwarded_from_*_id columns are never emitted.
        "forwarded_from_name": message.forwarded_from_name,
    }
