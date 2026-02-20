from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import UploadFile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.api.validation import (
    ensure_exists,
    raise_forbidden,
    raise_http_error,
    raise_validation_error,
)
from app.api.websocket import (
    build_presence_map,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
    notify_new_message,
)
from app.core.config import settings
from app.core.exceptions import BusinessRuleViolation
from app.models.chat import Attachment, Chat, Message
from app.models.models import User
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatMaintenanceResult,
    ChatResponse,
    ChatsListOut,
    MessageResponse,
    MessagesListOut,
    PresenceStatus,
)
from app.services.notifications import create_notifications_for_users
from app.utils.files import delete_static_file, save_attachment


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ChatRepository(session)

    async def _cleanup_orphaned_files(self, urls: list[str]) -> None:
        tasks = [delete_static_file(url) for url in urls if url]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _collect_attachment_urls(self, chat: Chat) -> list[str]:
        # Helper that assumes chat.messages are loaded
        urls: list[str] = []
        for message in chat.messages:
            for attachment in message.attachments:
                if attachment.url:
                    urls.append(attachment.url)
        return urls

    async def _process_chat_upload(
        self, upload: UploadFile, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, object]:
        meta = await save_attachment(
            upload,
            "chat_uploads",
            f"chat_{chat_id}",
            locale=locale,
            allowed_mime_types=settings.chat_attachment_allowed_mime_types_set,
            allowed_extensions=settings.chat_attachment_allowed_extensions_set,
            max_size_bytes=settings.chat_attachment_max_size_bytes,
            return_meta=True,
        )
        if not isinstance(meta, dict):
            raise_http_error(500, "errors.chat.attachment_failed", str(locale or "en"))

        detected_type = str(meta.get("detected_type") or meta.get("content_type") or "")
        file_type = "file"
        if detected_type.startswith("image/"):
            file_type = "image"
        elif detected_type.startswith("video/"):
            file_type = "video"

        return {
            "url": str(meta.get("url") or ""),
            "file_type": file_type,
            "filename": str(meta.get("filename") or upload.filename or "attachment"),
            "size": int(str(meta.get("size") or 0)),
        }

    async def get_chats(
        self, user: User, cursor: str | None, limit: int
    ) -> ChatsListOut:
        """
        Fetch chat list for a user, including metadata and last messages.

        Args:
            user: The current authenticated user.
            cursor: Pagination cursor.
            limit: Maximum number of chats.

        Returns:
            A list of chats with unread counts, last message, and participant presence.
        """
        rows, has_more, next_cursor = await self.repository.get_chats_for_user(
            user.id, cursor, limit
        )

        # Collect participant IDs for presence
        participant_ids: set[uuid.UUID] = set()
        chat_data_map: dict[str, dict] = {}

        for row in rows:
            chat = row[0]
            unread_count = row[1] or 0
            last_message_id = row[2]

            for participant in chat.participants:
                participant_ids.add(participant.id)

            chat_data_map[str(chat.id)] = {
                "chat": chat,
                "unread_count": unread_count,
                "last_message_id": last_message_id,
            }

        # Fetch last messages efficiently
        last_message_ids = [
            d["last_message_id"] for d in chat_data_map.values() if d["last_message_id"]
        ]
        last_messages_map = await self.repository.get_last_messages(last_message_ids)

        # Build responses to get clean ChatResponse objects (without presence yet)
        pre_responses = []
        for chat_id, data in chat_data_map.items():
            chat = data["chat"]
            last_message = last_messages_map.get(data["last_message_id"])

            pre_responses.append(
                ChatResponse(
                    id=chat.id,
                    participants=chat.participants,
                    last_message=last_message,
                    unread_count=data["unread_count"],
                    created_at=chat.created_at,
                    updated_at=chat.updated_at,
                )
            )

        presence_map = await build_presence_map(
            participant_ids, session=self.repository.session
        )

        # Enrich with presence
        enriched_chats = []
        for chat_resp in pre_responses:
            l_msg = chat_resp.last_message
            if l_msg is not None:
                # Convert Message model to MessageResponse to include sender_presence
                l_msg = MessageResponse(
                    id=l_msg.id,
                    chat_id=l_msg.chat_id,
                    sender_id=l_msg.sender_id,
                    content=l_msg.content,
                    created_at=l_msg.created_at,
                    read_status=l_msg.read_status,
                    sender=l_msg.sender,
                    attachments=l_msg.attachments,
                    sender_presence=presence_map.get(l_msg.sender_id),
                )

            participant_status = {}
            for participant in chat_resp.participants:
                participant_status[participant.id] = presence_map.get(
                    participant.id, PresenceStatus()
                )

            enriched_chats.append(
                ChatResponse(
                    **chat_resp.model_dump(exclude={"last_message", "presence"}),
                    last_message=l_msg,
                    presence=participant_status,
                )
            )

        return ChatsListOut(
            items=enriched_chats,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def create_chat(
        self, user: User, participant_id: uuid.UUID | None, locale: str
    ) -> ChatResponse:
        """
        Create a new chat or return an existing one.

        Args:
            user: The current authenticated user.
            participant_id: The ID of the user to chat with.
            locale: Locale for error messages.

        Returns:
            The chat details including participants and presence.
        """
        if not participant_id:
            raise_validation_error(
                "errors.chat.missing_participant", locale
            )  # defensive

        if participant_id == user.id:
            raise_validation_error("errors.chat.self_chat", locale)

        participant = await self.repository.get_user(participant_id)
        ensure_exists(participant, "users", locale)
        assert participant is not None

        from app.core.rate_limit import _get_shared_client

        redis_client = await _get_shared_client(settings.rate_limit_storage_uri)

        if not user.id or not participant_id:
            raise BusinessRuleViolation("errors.chat.invalid_participants")

        min_id, max_id = sorted([user.id.int, participant_id.int])
        lock_name = f"chat_init:{min_id}:{max_id}"

        async with redis_client.lock(lock_name, timeout=5):
            existing_chat = await self.repository.find_existing_dm(
                user.id, participant_id
            )
            if existing_chat:
                # We don't have presence/unread count readily available for existing chat
                # return here in the original code, but we should probably try to be
                # consistent?
                # Original code just returned basic ChatResponse. We'll stick to that for
                # now.
                return ChatResponse(
                    id=existing_chat.id,
                    participants=existing_chat.participants,
                    created_at=existing_chat.created_at,
                    updated_at=existing_chat.updated_at,
                )

            new_chat = await self.repository.create_chat([user, participant])
            await self.session.commit()
            await self.session.refresh(new_chat)

        # Invalidate caches for participants and the new chat
        participant_ids = [p.id for p in new_chat.participants]
        await invalidate_chat_participants_cache(new_chat.id)
        await invalidate_presence_audience_cache(*participant_ids)

        presence_map = await build_presence_map(
            [p.id for p in new_chat.participants], session=self.repository.session
        )

        return ChatResponse(
            id=new_chat.id,
            participants=new_chat.participants,
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            presence={
                p.id: presence_map.get(p.id, PresenceStatus())
                for p in new_chat.participants
            },
        )

    async def get_chat_details(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatResponse:
        """
        Get details for a specific chat.

        Args:
            chat_id: The UUID of the chat.
            user: The current authenticated user.
            locale: Locale for error messages.

        Returns:
            Chat details including unread count and presence.

        Raises:
            HTTPException: If chat not found or user not a participant.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        unread_count = await self.repository.get_unread_count(chat_id, user.id)
        last_message = await self.repository.get_last_message(chat_id)

        presence_map = await build_presence_map(
            [p.id for p in chat.participants], session=self.repository.session
        )
        participant_status = {
            p.id: presence_map.get(p.id, PresenceStatus()) for p in chat.participants
        }

        # Need to convert last_message to response if we want presence on it?
        # The schema definition allows Message model, but `sender_presence` is extra.
        # Original code didn't seem to enrich last_message in get_chat, only in
        # get_chats list?
        # Correction: The original get_chat returned ChatResponse which has
        # last_message.
        # Original code for get_chat just returned last_message (ORM object).

        return ChatResponse(
            id=chat.id,
            participants=chat.participants,
            last_message=last_message,
            unread_count=unread_count,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            presence=participant_status,
        )

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user: User,
        cursor: str | None,
        limit: int,
        locale: str,
    ) -> MessagesListOut:
        """
        Fetch messages for a chat.

        Args:
            chat_id: The UUID of the chat.
            user: The current authenticated user.
            cursor: Pagination cursor.
            limit: Maximum messages to return.
            locale: Locale for error messages.

        Returns:
            List of messages with sender data and presence.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        messages, has_more, next_cursor = await self.repository.get_messages(
            chat_id, cursor, limit
        )

        # Reverse for display order (asc)
        messages = list(reversed(messages))

        presence_map = await build_presence_map(
            {msg.sender_id for msg in messages}, session=self.repository.session
        )

        response_items = [
            MessageResponse(
                id=msg.id,
                chat_id=msg.chat_id,
                sender_id=msg.sender_id,
                content=msg.content,
                created_at=msg.created_at,
                read_status=msg.read_status,
                sender=msg.sender,
                attachments=msg.attachments,
                sender_presence=presence_map.get(msg.sender_id),
            )
            for msg in messages
        ]

        return MessagesListOut(
            items=response_items,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
    ) -> MessageResponse:
        """
        Send a new message to a chat.

        Args:
            chat_id: The UUID of the chat.
            user: The sender.
            content: Text content of the message.
            files: List of file attachments.
            locale: Locale for error messages.

        Returns:
            The created message with attachment metadata.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        uploads = files or []
        if len(uploads) > int(settings.chat_attachment_max_files):
            raise_validation_error("errors.files.too_many_attachments", locale)

        if not content.strip() and not uploads:
            raise_validation_error("errors.chat.empty_message", locale)

        message = Message(
            chat_id=chat_id,
            sender_id=user.id,
            content=content,
        )
        # We need message ID for attachments, so we create it via repo or just add
        # to session
        # Repo.create_message calls flush which gives ID.
        await self.repository.create_message(message)

        saved_urls: list[str] = []
        try:
            for upload in uploads:
                meta = await self._process_chat_upload(upload, chat_id, locale=locale)
                saved_urls.append(str(meta["url"]))
                attachment = Attachment(
                    message_id=message.id,
                    url=str(meta["url"]),
                    file_type=str(meta["file_type"]),
                    filename=str(meta["filename"]),
                    size=int(str(meta["size"])),
                )
                self.repository.add(attachment)

            await self.repository.update_timestamp(chat, datetime.now(UTC))
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            await self._cleanup_orphaned_files(saved_urls)
            raise

        await self.repository.refresh(message)
        await self.repository.refresh(message)

        # Notifications
        await notify_new_message(message, exclude_user_id=user.id)

        other_participants = [p.id for p in chat.participants if p.id != user.id]
        if other_participants:
            sender_name = (user.profile and user.profile.full_name) or "User"
            body_preview = content[:100] + "..." if len(content) > 100 else content
            await create_notifications_for_users(
                self.repository.session,
                title=sender_name,
                body=body_preview,
                type="chat.message",
                url=f"/messenger/{chat_id}",
                tag=f"chat:{chat_id}",
                user_ids=other_participants,
                topic="chat",
                payload_data={
                    "chatId": chat_id,
                    "senderId": user.id,
                    "messageId": message.id,
                },
            )

        presence_map = await build_presence_map(
            [message.sender_id], session=self.repository.session
        )

        return MessageResponse(
            id=message.id,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            content=message.content,
            created_at=message.created_at,
            read_status=message.read_status,
            sender=message.sender,
            attachments=message.attachments,
            sender_presence=presence_map.get(message.sender_id),
        )

    async def mark_read(self, chat_id: uuid.UUID, user: User, locale: str) -> None:
        """
        Mark all messages in a chat as read by the user.

        Args:
            chat_id: The UUID of the chat.
            user: The current authenticated user.
            locale: Locale for error messages.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        await self.repository.mark_messages_read(chat_id, user.id)
        await self.repository.commit()

    async def clear_history(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """
        Delete all messages in a chat (but keep the chat).

        Args:
            chat_id: The UUID of the chat.
            user: The requesting user.
            locale: Locale for error messages.

        Returns:
            Result summary including count of deleted items.
        """
        # Load messages to collect attachments
        chat = await self.repository.get_by_id(chat_id, load_messages=True)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        attachment_urls = await self._collect_attachment_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        try:
            # We can't easily iterate and delete in pure repo without passing the list
            # or logic
            # Repo has delete_messages(list).
            # chat.messages is available.
            await self.repository.delete_messages(list(chat.messages))
            await self.repository.update_timestamp(chat, datetime.now(UTC))
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self._cleanup_orphaned_files(attachment_urls)

        return ChatMaintenanceResult(
            chat_id=chat.id,
            status="cleared",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )

    async def delete_chat(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """
        Permanently delete a chat.

        Args:
            chat_id: The UUID of the chat.
            user: The requesting user.
            locale: Locale for error messages.

        Returns:
            Result summary including count of deleted items.
        """
        chat = await self.repository.get_by_id(chat_id, load_messages=True)
        ensure_exists(chat, "chat", locale)
        assert chat is not None

        if user.id not in {p.id for p in chat.participants}:
            raise_forbidden(locale, "errors.chat.not_participant")

        attachment_urls = await self._collect_attachment_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        # Collect participant IDs before deletion for cache invalidation
        participant_ids = [p.id for p in chat.participants]

        try:
            await self.repository.delete_chat(chat)
            await self.repository.commit()

            # Invalidate caches
            await invalidate_chat_participants_cache(chat_id)
            await invalidate_presence_audience_cache(*participant_ids)
        except Exception:
            await self.repository.rollback()
            raise

        await self._cleanup_orphaned_files(attachment_urls)

        return ChatMaintenanceResult(
            chat_id=chat_id,
            status="deleted",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )
