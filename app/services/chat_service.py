from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import UploadFile
    from app.core.protocols import AsyncDatabaseSession
    from app.models.models import User
    from app.models.chat import ChatMessage
    from app.schemas.chat import (
        ChatMaintenanceResult,
        ChatResponse,
        ChatsListOut,
        MessageResponse,
        MessagesListOut,
    )

from .chat.attachment_service import ChatAttachmentService
from .chat.command_service import ChatCommandService
from .chat.notification_service import ChatNotificationService
from .chat.query_service import ChatQueryService


class ChatService:
    """Facade for chat operations, delegating to specialized sub-services. (TD-1)"""

    def __init__(self, session: AsyncDatabaseSession):
        self.session = session
        self.attachments = ChatAttachmentService()
        self.notifications = ChatNotificationService(session)
        self.queries = ChatQueryService(session)
        self.commands = ChatCommandService(
            session, self.attachments, self.notifications
        )

    # ── Queries ──

    async def get_chats(
        self, user: User, cursor: str | None, limit: int
    ) -> ChatsListOut:
        return await self.queries.get_chats(user, cursor, limit)

    async def get_chat_details(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatResponse:
        return await self.queries.get_chat_details(chat_id, user, locale)

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user: User,
        cursor: str | None,
        limit: int,
        locale: str,
    ) -> MessagesListOut:
        return await self.queries.get_messages(chat_id, user, cursor, limit, locale)

    # ── Commands ──

    async def create_chat(
        self, user: User, participant_id: uuid.UUID | None, locale: str
    ) -> ChatResponse:
        return await self.commands.create_chat(user, participant_id, locale)

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
    ) -> MessageResponse:
        return await self.commands.send_message(chat_id, user, content, files, locale)

    async def mark_read(self, chat_id: uuid.UUID, user: User, locale: str) -> None:
        return await self.commands.mark_read(chat_id, user, locale)

    async def clear_history(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        return await self.commands.clear_history(chat_id, user, locale)

    async def delete_chat(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        return await self.commands.delete_chat(chat_id, user, locale)
