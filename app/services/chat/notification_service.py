from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.protocols import AsyncDatabaseSession
    from app.models.chat import Message
    from app.models.models import User
    from app.schemas.dtos import ChatParticipantDTO

from app.api.websocket import notify_new_message
from app.services.notifications import create_notifications_for_users


class ChatNotificationService:
    """Handles real-time and push notifications for chat events. (TD-1)"""

    def __init__(self, session: AsyncDatabaseSession):
        self.session = session

    async def notify_new_message(
        self,
        message: Message,
        chat_participants: Sequence[User | ChatParticipantDTO],
        sender: User,
    ) -> None:
        """Notify participants about a new message."""
        # WebSocket real-time notification
        await notify_new_message(message, exclude_user_id=sender.id)

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
                    "chatId": message.chat_id,
                    "senderId": sender.id,
                    "messageId": message.id,
                },
            )
