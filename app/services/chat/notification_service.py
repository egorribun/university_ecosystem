"""Chat notification service — fan-out for new-message events.

Two delivery channels run in parallel for every new message:

1. WebSocket broadcast via ``ws_manager.broadcast_to_chat`` — every
   connected participant *except the sender* receives a serialised
   message payload in real time.
2. Push notification via ``create_notifications_for_users`` — every
   non-sender participant gets an in-app + push entry. UUIDs in
   ``payload_data`` are stringified because UUID is not natively
   JSON-serialisable.

The body preview is truncated at 100 chars + "..." to keep push payloads
under platform-imposed size limits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any  # TD-23-04 (audit 2026-03-25 Wave 23)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.protocols import AsyncDatabaseSession
    from app.models import User
    from app.models.chat import Message
    from app.schemas.dtos import ChatParticipantDTO

from app.api.ws.connection_manager import manager as ws_manager
from app.api.ws.presence import build_presence_map
from app.api.ws.serializers import serialize_message
from app.services.notifications import create_notifications_for_users


class ChatNotificationService:
    """Handles real-time and push notifications for chat events. (TD-1)"""

    def __init__(self, session: AsyncDatabaseSession) -> None:
        self.session = session

    async def notify_new_message(
        self,
        message: Message,
        chat_participants: Sequence[User | ChatParticipantDTO],
        sender: User,
        replied: Any = None,
    ) -> None:
        """Notify participants about a new message.

        Wave 207 — ``replied`` is the replied-to message (a MessageDTO, loaded by
        handle_message_sent) or None; it is passed to serialize_message so the
        recipient's live new_message bubble carries the reply quote preview.
        """
        # WebSocket real-time notification
        presence = await build_presence_map([message.sender_id])
        await ws_manager.broadcast_to_chat(
            message.chat_id,
            {
                "type": "new_message",
                "chat_id": str(message.chat_id),
                "message": serialize_message(message, presence, replied=replied),
            },
            exclude_user_id=sender.id,
        )

        # Push Notification
        other_participants = [p.id for p in chat_participants if p.id != sender.id]
        if other_participants:
            sender_name = (sender.profile and sender.profile.full_name) or "User"
            content = message.content or ""
            body_preview = content[:100] + "..." if len(content) > 100 else content

            await create_notifications_for_users(
                self.session,
                title=sender_name,
                body=body_preview,
                type="chat.message",
                url=f"/messenger/{message.chat_id}",
                tag=f"chat:{message.chat_id}",
                user_ids=other_participants,
                topic="chat",
                payload_data={
                    # HIGH-W19: wrap UUID fields with str() to avoid JSON
                    # serialization errors — UUID is not natively JSON-serialisable.
                    "chatId": str(message.chat_id),
                    "senderId": str(sender.id),
                    "messageId": str(message.id),
                },
            )
