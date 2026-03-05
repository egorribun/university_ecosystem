"""WebSocket message serializers and presence map builder.

TD-9 / MOD-9 (audit 2026-03-05): Extracted from app/api/websocket.py.
Single responsibility: convert domain objects to WebSocket-wire format.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.core.database import async_session
from app.models.chat import Message
from app.repositories.session_repository import SessionRepository
from app.schemas.chat import ChatParticipant, PresenceStatus

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.core.protocols import AsyncDatabaseSession


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
