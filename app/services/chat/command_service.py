from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from fastapi import UploadFile

    from app.models.chat import Attachment
    from app.models.models import User
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.chat import (
        AttachmentResponse,
        ChatMaintenanceResult,
        ChatParticipant,
        ChatResponse,
        MessageResponse,
    )

    from .attachment_service import ChatAttachmentService
    from .notification_service import ChatNotificationService

from app.api.validation import (
    ensure_exists,
    raise_forbidden,
    raise_validation_error,
)
from app.api.ws.connection_manager import manager as ws_manager
from app.api.ws.presence import (
    build_presence_map,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
)
from app.core.config import settings
from app.core.exceptions import BusinessRuleViolation
from app.models.chat import Attachment
from app.models.models import Message
from app.schemas.chat import (
    ChatMaintenanceResult,
    ChatResponse,
    MessageResponse,
    PresenceStatus,
)


class ChatCommandService:
    """Handles write/modifying operations for chats and messages. (TD-1)"""

    def __init__(
        self,
        uow: UnitOfWork,
        attachment_service: ChatAttachmentService,
        notification_service: ChatNotificationService,
    ):
        self.uow = uow
        self.repository = uow.chats
        self.session = uow.session
        self.attachment_service = attachment_service
        self.notification_service = notification_service

    async def create_chat(
        self, user: User, participant_id: uuid.UUID | None, locale: str
    ) -> ChatResponse:
        """Create a new chat or return an existing one."""
        if not participant_id:
            raise_validation_error("errors.chat.missing_participant", locale)

        if participant_id == user.id:
            raise_validation_error("errors.chat.self_chat", locale)

        participant = await self.repository.get_user(participant_id)
        ensure_exists(participant, "users", locale)
        assert participant is not None  # nosec B101

        from app.deps.cache import get_cache_client

        cache_client = await get_cache_client()

        if not user.id or not participant_id:
            raise BusinessRuleViolation("errors.chat.invalid_participants")

        min_id, max_id = sorted([user.id, participant_id])
        lock_name = f"chat_init:{min_id}:{max_id}"

        async with cache_client.lock(lock_name, timeout=5, blocking_timeout=4):
            existing_chat = await self.repository.find_existing_dm(
                user.id, participant_id
            )
            if existing_chat:
                return ChatResponse(
                    id=existing_chat.id,
                    participants=cast(
                        "list[ChatParticipant]", existing_chat.participants
                    ),
                    created_at=existing_chat.created_at,
                    updated_at=existing_chat.updated_at,
                )

            new_chat = await self.repository.create_chat([user, participant])
            async with self.uow:
                await self.uow.commit()

        participant_ids = [p.id for p in new_chat.participants]
        await invalidate_chat_participants_cache(new_chat.id)
        await invalidate_presence_audience_cache(*participant_ids)

        presence_map = await build_presence_map(
            [p.id for p in new_chat.participants], db=self.session
        )

        return ChatResponse(
            id=new_chat.id,
            participants=cast("list[ChatParticipant]", new_chat.participants),
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            presence={
                p.id: presence_map.get(p.id, PresenceStatus())
                for p in new_chat.participants
            },
        )

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
        idempotency_key: str | None = None,
    ) -> MessageResponse:
        """Send a new message to a chat.

        D-02 (audit 2026-03-08): Supports idempotent sends via the
        ``Idempotency-Key`` header.  If a key is provided and a cached response
        exists in Redis (TTL 24 h), it is returned immediately — no duplicate
        message is created.  The key is namespaced by ``(chat_id, user_id)`` to
        prevent cross-user and cross-chat replay attacks.
        """
        # ── Idempotency check (D-02) ────────────────────────────────────────
        _idempotency_cache_key: str | None = None
        if idempotency_key:
            import json as _json

            from app.deps.cache import get_cache_client

            _cache = await get_cache_client()
            _idempotency_cache_key = (
                f"idempotency:msg:{chat_id}:{user.id}:{idempotency_key}"
            )
            _cached = await _cache.get(_idempotency_cache_key)
            if _cached:
                # BE-02 (audit 2026-03-08 Wave 5): Cache now stores only the
                # message ID (slim format) rather than the full serialised
                # MessageResponse.  This prevents message content from sitting
                # unencrypted in Redis for 24 h.  Re-fetch the full message from
                # the DB on cache hit — one extra indexed PK lookup is negligible
                # compared to avoiding plaintext content storage in the cache.
                try:
                    _hit = _json.loads(_cached)
                    _msg_id = uuid.UUID(_hit["message_id"])
                except (ValueError, KeyError, TypeError):
                    # Legacy entry: full JSON from before BE-02 — fall through to
                    # re-send path (idempotency protection degraded, not broken).
                    pass
                else:
                    _full = await self.repository.get_message_by_id(_msg_id)
                    if _full is not None:
                        return MessageResponse(
                            **_full.model_dump(),
                            sender_presence=PresenceStatus(
                                active=ws_manager.is_online(_full.sender_id)
                            ),
                        )

        # Check existence first (for correct 404 reporting)
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # nosec B101

        # Check participation (TD-4 security audit)
        is_participant = await self.repository.check_participant(chat_id, user.id)
        if not is_participant:
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
        await self.repository.create_message(message)

        # D-03 (audit 2026-03-08): Hard deadline on each individual upload so a
        # hung ClamAV scan or MinIO connection does not block the ASGI worker
        # forever.  30s is generous for normal uploads and tight enough to
        # surface genuine infrastructure failures quickly.
        _UPLOAD_TIMEOUT_SECONDS = 30.0

        saved_urls: list[str] = []
        try:
            for upload in uploads:
                try:
                    async with asyncio.timeout(_UPLOAD_TIMEOUT_SECONDS):
                        meta = await self.attachment_service.process_upload(
                            upload, chat_id, locale=locale
                        )
                except TimeoutError:
                    await self.attachment_service.cleanup_files(saved_urls)
                    raise_validation_error("errors.files.upload_timeout", locale)
                saved_urls.append(str(meta["url"]))
                attachment = Attachment(
                    message=message,
                    url=str(meta["url"]),
                    file_type=str(meta["file_type"]),
                    filename=str(meta["filename"]),
                    size=int(str(meta["size"])),
                )
                self.repository.add(attachment)

            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))
            async with self.uow:
                await self.uow.commit()
        except Exception:
            await self.uow.rollback()
            await self.attachment_service.cleanup_files(saved_urls)
            raise

        # Reload message with attachments for the response
        reloaded = await self.repository.get_last_messages([message.id])
        full_message = reloaded.get(message.id)

        if not full_message:
            # Fallback if something went wrong, though unlikely
            await self.repository.refresh(message)
            msg_data = MessageResponse(
                id=message.id,
                chat_id=message.chat_id,
                sender_id=message.sender_id,
                content=message.content,
                created_at=message.created_at,
                read_status=message.read_status,
                sender=message.sender,
                attachments=cast("list[AttachmentResponse]", message.attachments),
                sender_presence=PresenceStatus(
                    active=ws_manager.is_online(message.sender_id)
                ),
            )
        else:
            msg_data = MessageResponse(
                **full_message.model_dump(),
                sender_presence=PresenceStatus(
                    active=ws_manager.is_online(message.sender_id)
                ),
            )

        # Notify participants
        await self.notification_service.notify_new_message(
            message, chat.participants, user
        )

        # ── Idempotency store (D-02 / BE-02) ────────────────────────────────
        # BE-02 (audit 2026-03-08 Wave 5): Store only the message ID rather than
        # the full serialised MessageResponse.  Storing plaintext message content
        # in Redis for 24 h is a data-protection risk: if Redis is exfiltrated,
        # attackers gain access to all recently sent messages.  On cache hit we
        # re-fetch the full message from the DB (one PK lookup — negligible cost).
        if _idempotency_cache_key:
            import json as _json

            from app.deps.cache import get_cache_client

            _cache = await get_cache_client()
            _slim = _json.dumps({"message_id": str(msg_data.id)})
            await _cache.setex(
                _idempotency_cache_key,
                86400,  # 24 h — covers any reasonable client retry window
                _slim,
            )

        return msg_data

    async def mark_read(self, chat_id: uuid.UUID, user: User, locale: str) -> None:
        """Mark all messages in a chat as read by the user."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # nosec B101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        await self.repository.mark_messages_read(chat_id, user.id)
        async with self.uow:
            await self.uow.commit()

    async def clear_history(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """Delete all messages in a chat (but keep the chat)."""
        chat = await self.repository.get_by_id(chat_id, load_messages=True)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # nosec B101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        attachment_urls = await self.attachment_service.collect_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        try:
            await self.repository.delete_messages([m.id for m in chat.messages])
            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))
            async with self.uow:
                await self.uow.commit()
        except Exception:
            await self.uow.rollback()
            raise

        await self.attachment_service.cleanup_files(attachment_urls)

        return ChatMaintenanceResult(
            chat_id=chat.id,
            status="cleared",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )

    async def delete_chat(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """Permanently delete a chat."""
        chat = await self.repository.get_by_id(chat_id, load_messages=True)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # nosec B101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        attachment_urls = await self.attachment_service.collect_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        p_ids = [p.id for p in chat.participants]

        try:
            await self.repository.delete_chat(chat_id)
            async with self.uow:
                await self.uow.commit()

            await invalidate_chat_participants_cache(chat_id)
            await invalidate_presence_audience_cache(*p_ids)
        except Exception:
            await self.uow.rollback()
            raise

        # R-02 (audit 2026-03-08): Invalidate ws-hub auth cache immediately after
        # deleting the chat so participants lose room authorization without waiting
        # for the 60s TTL to expire (BOLA-01 — stale cache window after deletion).
        # BE-01 (audit 2026-03-08 Wave 5): Use the module-level singleton via
        # invalidate_ws_hub_cache() — creating a new WsHubClient() per call
        # bypasses persistent connection pooling (RZ-F-04) and leaks httpx clients.
        # asyncio.gather parallelises N invalidations instead of serial awaits.
        from app.services.ws_hub_client import invalidate_ws_hub_cache

        await asyncio.gather(
            *(invalidate_ws_hub_cache(str(_pid), str(chat_id)) for _pid in p_ids),
            return_exceptions=True,  # one failure must not abort the rest
        )

        await self.attachment_service.cleanup_files(attachment_urls)

        return ChatMaintenanceResult(
            chat_id=chat_id,
            status="deleted",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )
