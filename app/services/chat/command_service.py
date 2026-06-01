"""Chat message and maintenance commands.

TD-W9-01 (audit 2026-03-16): Chat *creation* logic (Redis DM lock, presence
hydration) lives in ChatCreationService.  This service owns message dispatch
and maintenance operations (mark-read, clear-history, delete-chat).
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import (  # TD-23-04 (audit 2026-03-25 Wave 23)
    TYPE_CHECKING,
    Any,
    Protocol,
    cast,
)

if TYPE_CHECKING:
    from fastapi import UploadFile

    from app.models import User
    from app.models.chat import Attachment
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.chat import (
        AttachmentResponse,
        ChatMaintenanceResult,
        MessageResponse,
    )

    from .notification_service import ChatNotificationService

from app.api.validation import (
    ensure_exists,
    raise_forbidden,
    raise_not_found,
    raise_validation_error,
)
from app.api.ws.connection_manager import manager as ws_manager
from app.api.ws.presence import (
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
)
from app.core.config import settings
from app.core.events import EventEmitterMixin, MessageSent
from app.models import Message
from app.models.chat import Attachment
from app.models.enums import UserRole
from app.schemas.chat import (
    ChatMaintenanceResult,
    MessageResponse,
    PresenceStatus,
    ReplyPreview,
)


def _make_idempotency_key(
    chat_id: uuid.UUID, user_id: uuid.UUID, client_key: str
) -> str:
    """Build a Redis idempotency key whose components cannot be reverse-enumerated.

    RZ-W10-11: When IDEMPOTENCY_HMAC_SECRET is set, the raw string is signed
    with HMAC-BLAKE2b so that an observer of the Idempotency-Key header cannot
    enumerate (chat_id, user_id) pairs by brute-forcing client_key values.
    Falls back to plain BLAKE2b when the secret is empty (backward-compat).

    The ``idm:msg:`` prefix keeps the key recognisable in Redis MONITOR /
    keyspace notifications without leaking chat_id or user_id.
    """
    import hmac as _hmac

    raw = f"{chat_id}:{user_id}:{client_key}"
    secret = settings.idempotency_hmac_secret
    if secret:
        digest = _hmac.new(secret.encode(), raw.encode(), hashlib.blake2b).hexdigest()  # type: ignore[arg-type]
    else:
        digest = hashlib.blake2b(raw.encode(), digest_size=16).hexdigest()
    return f"idm:msg:{digest}"


if TYPE_CHECKING:
    from fastapi import UploadFile


class AttachmentProcessorProtocol(Protocol):
    async def process_upload(
        self, upload: UploadFile, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]: ...
    async def cleanup_files(self, urls: list[str]) -> None: ...
    async def collect_urls(
        self, chat: Any
    ) -> list[str]: ...  # Any: accepts Chat or ChatDTO


class ChatMessageDispatcher:
    """Message dispatch commands.

    TD-W9-01: Refactored from the legacy ChatCommandService to satisfy the Single
    Responsibility Principle. Maintenance tasks extracted to ChatMaintenanceService.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        attachment_service: AttachmentProcessorProtocol,
        notification_service: ChatNotificationService,
    ) -> None:
        self.uow = uow
        self.repository = uow.chats
        self.session = uow.session
        self.attachment_service = attachment_service
        self.notification_service = notification_service

    async def send_message(
        self,
        chat_id: uuid.UUID,
        user: User,
        content: str,
        files: list[UploadFile],
        locale: str,
        idempotency_key: str | None = None,
        reply_to_message_id: uuid.UUID | None = None,
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
            _idempotency_cache_key = _make_idempotency_key(
                chat_id, user.id, idempotency_key
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
                except (ValueError, KeyError, TypeError):  # RZ-28-01
                    # Legacy entry: full JSON from before BE-02 — fall through to
                    # re-send path (idempotency protection degraded, not broken).
                    pass
                else:
                    _full = await self.repository.get_message_by_id(_msg_id)
                    if _full is not None:
                        # Wave 207 — exclude the raw replied_to DTO from the spread
                        # (MessageResponse is extra="forbid"); inject the lean preview.
                        return MessageResponse(
                            **_full.model_dump(exclude={"replied_to"}),
                            reply_to=ReplyPreview.from_message(_full.replied_to),
                            sender_presence=PresenceStatus(
                                active=ws_manager.is_online(_full.sender_id)
                            ),
                        )

        # Check existence first (for correct 404 reporting)
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        # Check participation (TD-4 security audit)
        is_participant = await self.repository.check_participant(chat_id, user.id)
        if not is_participant:
            raise_forbidden(locale, "errors.chat.not_participant")

        # Wave 207 — if this is a reply, the target must exist AND be in THIS chat.
        # message_exists_in_chat checks both (id == … AND chat_id == …) via EXISTS,
        # so a reply to a message in another chat — or a bogus id — 404s before any
        # DB write. The 404-before-insert also avoids a mid-transaction FK error on
        # the SET NULL self-FK.
        if reply_to_message_id is not None:
            target_in_chat = await self.repository.message_exists_in_chat(
                reply_to_message_id, chat_id
            )
            if not target_in_chat:
                raise_not_found("message", locale)

        uploads = files or []
        if len(uploads) > int(settings.chat_attachment_max_files):
            raise_validation_error("errors.files.too_many_attachments", locale)

        # TD-14-05 (audit 2026-03-23): Guard total payload size before any
        # S3 / ClamAV I/O.  Prevents 5 × 15 MB = 75 MB concurrent uploads
        # that would saturate the scanner and object-storage pipeline.
        # UploadFile.size is set by FastAPI from the Content-Length of each
        # multipart part; falls back to 0 if the client did not send it
        # (the per-file check inside process_upload() enforces the hard cap).
        total_size = sum(u.size or 0 for u in uploads)
        if total_size > settings.chat_attachment_max_total_bytes:
            raise_validation_error("errors.files.total_size_exceeded", locale)

        if not content.strip() and not uploads:
            raise_validation_error("errors.chat.empty_message", locale)

        # RZ-W10-10: Reject oversized messages before any DB or S3 I/O to
        # prevent storage DoS via multi-MB message bodies.
        if len(content) > settings.chat_max_message_length:
            raise_validation_error("errors.chat.message_too_long", locale)

        # D-03 (audit 2026-03-08): Hard deadline on each individual upload so a
        # hung ClamAV scan or MinIO connection does not block the ASGI worker
        # forever.  30s is generous for normal uploads and tight enough to
        # surface genuine infrastructure failures quickly.
        _UPLOAD_TIMEOUT_SECONDS = 30.0

        # RACE-BE-01 (audit Wave 10): Reserve the idempotency slot BEFORE any
        # upload so that failures in Phase 1 OR Phase 2 both hit the same except
        # clause and release the slot.  Without pre-reservation the slot is only
        # written on success (line ~300); a Phase-2 DB failure leaves no record
        # and the next retry re-uploads — creating duplicate S3 objects.
        #
        # Redis SET NX: "pending" marks the slot as in-flight.  TTL 300 s covers
        # the maximum upload + DB write time with room to spare.  An existing
        # "pending" value means a concurrent/retried request — we fall through to
        # the normal flow; the DB unique constraint is the final arbiter.
        if _idempotency_cache_key:
            import json as _json

            from app.deps.cache import get_cache_client

            _cache = await get_cache_client()
            await _cache.set(
                _idempotency_cache_key,
                _json.dumps({"status": "pending"}),
                nx=True,
                ex=300,
            )

        # ── Phase 1 + Phase 2 wrapped together ───────────────────────────────
        # Both phases share the same exception handler so that a Phase-2 failure
        # also triggers file cleanup and idempotency slot release — closing the
        # RACE-BE-01 window.

        processed_attachments: list[dict[str, Any]] = []
        saved_urls: list[str] = []
        try:
            # ── Phase 1: Upload processing (NO DB writes yet) ─────────────────
            # Process ALL uploads before touching the DB.  If any upload fails,
            # no Message record exists and no rollback is required.
            if uploads:
                sem = asyncio.Semaphore(3)

                # MOD-23-04 (audit 2026-03-25 Wave 23): structured concurrency via TaskGroup
                # — if any upload fails the remaining uploads are cancelled immediately,
                # which is the correct all-or-nothing semantic for Phase 1 (no partial
                # attachment sets).  Replaces gather(return_exceptions=True) + manual
                # error inspection loop.
                async def _upload_task(upload: UploadFile) -> None:
                    async with sem, asyncio.timeout(_UPLOAD_TIMEOUT_SECONDS):
                        res = await self.attachment_service.process_upload(
                            upload, chat_id, locale=locale
                        )
                        saved_urls.append(str(res["url"]))
                        processed_attachments.append(res)

                try:
                    async with asyncio.TaskGroup() as tg:
                        for u in uploads:
                            tg.create_task(_upload_task(u))
                except* TimeoutError:
                    raise_validation_error("errors.files.upload_timeout", locale)

        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — cleans up partial uploads then re-raises (reviewed TD-27-04)
            # Phase 1 failure: clean up any partial uploads and release slot.
            if saved_urls:
                await self.attachment_service.cleanup_files(saved_urls)
            if _idempotency_cache_key:
                import json as _json

                from app.deps.cache import get_cache_client

                _cache = await get_cache_client()
                await _cache.delete(_idempotency_cache_key)
            raise

        # ── Phase 2: Atomic DB write ─────────────────────────────────────────
        # All uploads succeeded — now write Message + Attachments + MessageSent
        # event in a single transaction.  If this fails we clean up the uploaded
        # files (best-effort) and release the idempotency pending slot so the
        # next retry can start fresh — closing the RACE-BE-01 window.
        try:
            message = Message(
                chat_id=chat_id,
                sender_id=user.id,
                content=content,
                reply_to_message_id=reply_to_message_id,  # Wave 207
            )
            await self.repository.create_message(message)

            # ARCH-BE-01 (audit Wave 10): record_event() MUST be called BEFORE any
            # SQL query that could trigger an autoflush (e.g. update_timestamp_by_id
            # below issues an UPDATE which causes SQLAlchemy to autoflush the session
            # before executing it).  Once the autoflush fires, `message` leaves
            # session.new and may not be in session.dirty — the `after_flush` listener
            # in capture_domain_events() scans only `new | dirty | deleted`, so any
            # event registered after that flush is silently dropped and never lands in
            # the `stored_events` (outbox) table.
            #
            # W205 SW-A: that premise was in fact FALSE here — repository.create_message()
            # (above) ALREADY flushes the message, so by this point it is persistent
            # (out of session.new), and record_event sets a non-mapped attr (no dirty
            # mark), so capture missed it and the outbox stayed empty. The real fix is
            # central (app/core/events.py): record_event now tracks the emitter on
            # session.info so capture catches it regardless of flush ordering. This
            # ordering is therefore no longer load-bearing, but is kept as defence.
            #
            # UUID7PrimaryKeyMixin uses a Python-side default (generate_uuid7), so
            # message.id is populated by the __init__ constructor call above — it is
            # safe to reference here before the INSERT is flushed.
            #
            # Cast: Message inherits EventEmitterMixin (models/chat.py), but mypy
            # cannot resolve SQLAlchemy's multi-inheritance graph statically.
            cast(EventEmitterMixin, message).record_event(
                MessageSent(
                    message_id=message.id,
                    chat_id=message.chat_id,
                    sender_id=message.sender_id,
                    content_preview=message.content[:50],
                )
            )

            for meta in processed_attachments:
                attachment = Attachment(
                    message=message,
                    url=str(meta["url"]),
                    file_type=str(meta["file_type"]),
                    filename=str(meta["filename"]),
                    size=int(str(meta["size"])),
                )
                self.repository.add(attachment)

            # The UPDATE below triggers an SQLAlchemy autoflush — at that point
            # `message` (and its _pending_domain_events) are still in session.new,
            # so capture_domain_events() correctly creates the StoredEvent row and
            # adds it to the session.  Both Message and StoredEvent are committed
            # atomically in the uow.commit() call below.
            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))

            async with self.uow:
                await self.uow.commit()

        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — cleans up uploaded files then re-raises (reviewed TD-27-04)
            # RACE-BE-01: Phase 2 failed — clean up already-uploaded files and
            # release the idempotency slot so the next retry can re-upload fresh
            # copies rather than re-using orphaned S3 objects.
            if saved_urls:
                await self.attachment_service.cleanup_files(saved_urls)
            if _idempotency_cache_key:
                import json as _json

                from app.deps.cache import get_cache_client

                _cache = await get_cache_client()
                await _cache.delete(_idempotency_cache_key)
            raise

        # Reload message with attachments for the response
        reloaded = await self.repository.get_last_messages([message.id])
        full_message = reloaded.get(message.id)

        if not full_message:
            # Fallback if something went wrong, though unlikely
            await self.session.refresh(message)
            msg_data = MessageResponse(
                id=message.id,
                chat_id=message.chat_id,
                sender_id=message.sender_id,
                content=message.content,
                created_at=message.created_at,
                read_status=message.read_status,
                edited_at=message.edited_at,  # Wave 205 SW4 — W203 SW8 gotcha
                deleted_at=message.deleted_at,  # Wave 205 SW4 — W203 SW8 gotcha
                sender=message.sender,
                attachments=cast("list[AttachmentResponse]", message.attachments),
                sender_presence=PresenceStatus(
                    active=ws_manager.is_online(message.sender_id)
                ),
                # Wave 207 — degraded rare path (get_last_messages returned nothing);
                # replied_to isn't loaded here, so the quote preview is omitted. The
                # main + cache-hit paths carry it.
                reply_to=None,
            )
        else:
            msg_data = MessageResponse(
                # Wave 207 — exclude the raw replied_to DTO from the spread
                # (MessageResponse is extra="forbid"); inject the lean preview built
                # from the selectinload'd replied_to.
                **full_message.model_dump(exclude={"replied_to"}),
                reply_to=ReplyPreview.from_message(full_message.replied_to),
                sender_presence=PresenceStatus(
                    active=ws_manager.is_online(message.sender_id)
                ),
            )

        # RZ-F-11: Notification handling moved to OutboxWorker / EventHandlers
        # for reliability. Direct call removed.
        # await self.notification_service.notify_new_message(
        #     message, chat.participants, user
        # )

        # ── Idempotency store (D-02 / BE-02 / RACE-BE-01) ───────────────────
        # BE-02 (audit 2026-03-08 Wave 5): Store only the message ID rather than
        # the full serialised MessageResponse.  Storing plaintext message content
        # in Redis for 24 h is a data-protection risk: if Redis is exfiltrated,
        # attackers gain access to all recently sent messages.  On cache hit we
        # re-fetch the full message from the DB (one PK lookup — negligible cost).
        #
        # RACE-BE-01: Overwrite the "pending" placeholder set before Phase 1 with
        # the "completed" entry including message_id.  setex replaces regardless
        # of current value — atomic promotion from pending → completed.
        if _idempotency_cache_key:
            import json as _json

            from app.deps.cache import get_cache_client

            _cache = await get_cache_client()
            _slim = _json.dumps({"status": "completed", "message_id": str(msg_data.id)})
            await _cache.setex(
                _idempotency_cache_key,
                86400,  # 24 h — covers any reasonable client retry window
                _slim,
            )

        return msg_data


class ChatMaintenanceService:
    """Chat maintenance commands (mark-read, clear-history, delete-chat).

    Extracted from ChatCommandService to satisfy the Single Responsibility Principle.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        attachment_service: AttachmentProcessorProtocol,
    ) -> None:
        self.uow = uow
        self.repository = uow.chats
        self.attachment_service = attachment_service

    async def mark_read(self, chat_id: uuid.UUID, user: User, locale: str) -> None:
        """Mark all messages in a chat as read by the user."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        read_at, affected = await self.repository.mark_messages_read(chat_id, user.id)
        async with self.uow:
            await self.uow.commit()

        # Wave 203 SW4 — broadcast a chat-level read receipt so the other
        # participant's sent bubbles flip to "seen" live. Ephemeral tier
        # (inline ws_manager, like typing/presence) — NOT a domain event; a
        # missed frame self-heals on the next message refetch (read_at is a
        # persisted column). Gated on affected > 0 so repeated chat-opens with
        # nothing new don't churn the sender's "Seen ·" timestamp. Broadcast
        # AFTER commit so a sender that immediately refetches sees the persisted
        # value (read-your-write safety).
        if affected > 0:
            await ws_manager.broadcast_to_chat(
                chat_id,
                {
                    "type": "read",
                    "chat_id": str(chat_id),
                    "user_id": str(user.id),
                    "read_at": read_at.isoformat(),
                },
                exclude_user_id=user.id,
            )

    async def edit_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
        new_content: str,
        locale: str,
    ) -> None:
        """Edit a message's content (author-only) and broadcast it live.

        Wave 205 SW3 — copies the mark_read synchronous-broadcast pattern: participant
        check → repo edit → commit → gated broadcast AFTER commit (read-your-write).
        The repo's author-only WHERE means affected == 0 ⇒ not the author / missing /
        already deleted ⇒ 404 (raised before commit; nothing to persist).
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        edited_at, affected = await self.repository.edit_message(
            message_id, user.id, new_content
        )
        if affected == 0:
            raise_not_found("message", locale)

        async with self.uow:
            await self.uow.commit()

        # Wave 205 SW3 — broadcast message_edited SYNCHRONOUSLY after commit so the
        # edit flips live via the W204 bridge. exclude_user_id is omitted (broadcast
        # to all): the NATS mirror can't exclude per-recipient anyway, and the FE
        # cache-update is idempotent — the author's echo merely reconciles its
        # optimistic client-time edited_at to the authoritative server value. A missed
        # frame self-heals on refetch (edited_at is a persisted column).
        await ws_manager.broadcast_to_chat(
            chat_id,
            {
                "type": "message_edited",
                "message_id": str(message_id),
                "chat_id": str(chat_id),
                "content": new_content,
                "edited_at": edited_at.isoformat() if edited_at else None,
            },
        )

    async def soft_delete_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> None:
        """Soft-delete a message (author-only) and broadcast the tombstone live.

        Wave 205 SW3 — same synchronous-broadcast pattern as edit_message. The repo
        clears content + stamps deleted_at (D1 tombstone); affected == 0 ⇒ 404.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        deleted_at, affected = await self.repository.soft_delete_message(
            message_id, user.id
        )
        if affected == 0:
            raise_not_found("message", locale)

        async with self.uow:
            await self.uow.commit()

        await ws_manager.broadcast_to_chat(
            chat_id,
            {
                "type": "message_deleted",
                "message_id": str(message_id),
                "chat_id": str(chat_id),
                "deleted_at": deleted_at.isoformat() if deleted_at else None,
            },
        )

    async def add_reaction(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
        emoji: str,
        locale: str,
    ) -> None:
        """Add an emoji reaction (any participant, any message) and broadcast live.

        Wave 206 — same synchronous-broadcast pattern as mark_read/edit. Reactions
        are NOT author-gated, so a missing message can't surface as affected == 0;
        an explicit message_exists_in_chat check raises 404 BEFORE the INSERT (also
        avoids a mid-transaction FK IntegrityError on a bogus message_id). The
        repo's idempotent ON CONFLICT DO NOTHING means a repeat reaction yields
        is_new == False ⇒ no broadcast (no-op, 200).
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        if not await self.repository.message_exists_in_chat(message_id, chat_id):
            raise_not_found("message", locale)

        is_new = await self.repository.add_reaction(message_id, user.id, emoji)
        async with self.uow:
            await self.uow.commit()

        # Wave 206 — DELTA frame (the W203 read-frame archetype): carries the actor
        # + the change, NOT the resolved aggregate (reacted_by_me is per-viewer).
        # Gated on is_new so a duplicate reaction doesn't double-count downstream.
        # exclude_user_id excludes the actor from the in-process fan-out; the NATS
        # mirror can't exclude per-recipient, so the FE self-echo guard
        # (user_id === currentUserId → skip; the actor already patched
        # optimistically) is the real protection. A missed/duplicate delta self-
        # heals on the next GET /messages (the persisted aggregate is authoritative).
        if is_new:
            await ws_manager.broadcast_to_chat(
                chat_id,
                {
                    "type": "reaction_changed",
                    "chat_id": str(chat_id),
                    "message_id": str(message_id),
                    "user_id": str(user.id),
                    "emoji": emoji,
                    "action": "added",
                },
                exclude_user_id=user.id,
            )

    async def remove_reaction(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
        emoji: str,
        locale: str,
    ) -> None:
        """Remove an emoji reaction and broadcast the delta live.

        Wave 206 — idempotent: removing a non-existent reaction is a benign no-op
        (affected == 0 ⇒ no broadcast, 200; no existence 404 needed). Broadcast +
        exclude_user_id semantics mirror add_reaction.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        affected = await self.repository.remove_reaction(message_id, user.id, emoji)
        async with self.uow:
            await self.uow.commit()

        if affected > 0:
            await ws_manager.broadcast_to_chat(
                chat_id,
                {
                    "type": "reaction_changed",
                    "chat_id": str(chat_id),
                    "message_id": str(message_id),
                    "user_id": str(user.id),
                    "emoji": emoji,
                    "action": "removed",
                },
                exclude_user_id=user.id,
            )

    async def broadcast_typing(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> None:
        """Broadcast a 'typing' indicator to the OTHER chat participants (Wave 207).

        The frontend WS connects to ws-hub, whose allowedMessageTypes drops "typing"
        at its parse boundary (services/ws-hub client.go) — so a typing frame sent over
        the socket goes nowhere. This REST endpoint does the participant authz +
        broadcast the (now frontend-unreachable) in-process WS typing handler did
        (app/api/ws/dispatcher.py): broadcast_to_chat → W204 bridge → ws-hub chat.*
        fan-out → the other participants' live TypingIndicator. No DB write — typing is
        ephemeral. check_participant (a single EXISTS) is the light authz for this
        ~2/sec hot path; a non-participant (or unknown chat) → 403, no existence leak.
        The user_name resolution + frame shape mirror dispatcher.py exactly (profile is
        lazy="noload", so it falls back to the email when not eager-loaded).
        """
        if not await self.repository.check_participant(chat_id, user.id):
            raise_forbidden(locale, "errors.chat.not_participant")

        await ws_manager.broadcast_to_chat(
            chat_id,
            {
                "type": "typing",
                "chat_id": str(chat_id),
                "user_id": str(user.id),
                "user_name": getattr(user.profile, "full_name", None)
                if getattr(user, "profile", None)
                else str(user.email),
            },
            exclude_user_id=user.id,
        )

    def _require_group_participant(
        self, chat: Any, user: User, locale: str
    ) -> set[uuid.UUID]:
        """Authz gate for group member-management (Wave 209 G1).

        Authz-first: a non-participant gets 403 (no chat existence/type leak)
        BEFORE the chat-type check; a DM then gets 400 not_a_group. Returns the
        current (pre-change) participant id set for cache invalidation.
        """
        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")
        if chat.chat_type != "group":
            raise_validation_error("errors.chat.not_a_group", locale)
        return participant_ids

    async def add_participant(
        self,
        chat_id: uuid.UUID,
        user: User,
        new_user_id: uuid.UUID,
        locale: str,
    ) -> None:
        """Add a member to a group (Wave 209 G1 — any participant may add).

        After commit, invalidate the chat-participant cache + the new + existing
        members' presence-audience caches — the SECURITY invariant: broadcast_to_chat
        AND the ws-hub join-gate both read chat:{id}:participants, so a stale cache
        would lock the new member out of live frames (or keep a removed one in). No
        live roster frame is pushed (FE refetches ["chats"] after the 200 — G3 adds
        member-change frames). add_participant is idempotent (added == False ⇒ no
        membership change ⇒ skip the invalidation).
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = self._require_group_participant(chat, user, locale)

        target = await self.repository.get_user(new_user_id)
        ensure_exists(target, "users", locale)

        added = await self.repository.add_participant(chat_id, new_user_id)
        async with self.uow:
            await self.uow.commit()

        if added:
            await invalidate_chat_participants_cache(chat_id)
            await invalidate_presence_audience_cache(new_user_id, *participant_ids)

    async def remove_participant(
        self,
        chat_id: uuid.UUID,
        user: User,
        target_user_id: uuid.UUID,
        locale: str,
    ) -> None:
        """Remove a member from a group (Wave 209 G1).

        The owner (created_by) may remove anyone; any member may remove themselves
        (leave); anyone else → 403 remove_forbidden. After commit, invalidate the
        same caches as add (security invariant). Removing a non-member is a benign
        no-op (affected == 0 ⇒ skip the invalidation).
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = self._require_group_participant(chat, user, locale)

        is_self_leave = target_user_id == user.id
        is_owner = chat.created_by == user.id
        if not (is_self_leave or is_owner):
            raise_forbidden(locale, "errors.chat.remove_forbidden")

        affected = await self.repository.remove_participant(chat_id, target_user_id)
        async with self.uow:
            await self.uow.commit()

        if affected:
            await invalidate_chat_participants_cache(chat_id)
            await invalidate_presence_audience_cache(target_user_id, *participant_ids)

    async def rename_chat(
        self, chat_id: uuid.UUID, user: User, name: str, locale: str
    ) -> None:
        """Rename a group's display title (Wave 209 G1 — any participant may rename).

        No cache invalidation — the rename changes only the display name, not the
        roster (the participant cache holds ids). FE refetches the chat list. The
        RenameChat schema enforces min_length=1, but a whitespace-only name passes
        that and is blank after strip, so re-validate here.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        self._require_group_participant(chat, user, locale)

        clean_name = name.strip()
        if not clean_name:
            raise_validation_error("errors.chat.group_name_required", locale)

        await self.repository.rename_chat(chat_id, clean_name)
        async with self.uow:
            await self.uow.commit()

    async def clear_history(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """Delete all messages in a chat (but keep the chat)."""
        chat = await self.repository.get_by_id(chat_id, load_messages=True)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids and user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.not_participant")

        # RACE-02 Fix: DMs are shared state. Unilateral history destruction by a regular
        # participant allows bad actors to delete evidence from the victim's device.
        if user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.history_clear_forbidden_non_admin")

        attachment_urls = await self.attachment_service.collect_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        try:
            await self.repository.delete_messages([m.id for m in chat.messages])
            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))

            # PERF-W10-05: Durable cleanup via Outbox — StoredEvent is written in
            # the SAME transaction as message deletes.  OutboxWorker retries on
            # failure, preventing permanent file leaks if the process crashes
            # between the commit and the S3/static delete call.
            if attachment_urls:
                from app.core.events import AttachmentCleanupRequested as _ACR
                from app.models.domain_events import StoredEvent as _StoredEvent

                self.repository.add(
                    _StoredEvent(
                        event_type=_ACR.EVENT_TYPE,
                        aggregate_type="Chat",
                        aggregate_id=str(chat_id),
                        payload={
                            "chat_id": str(chat_id),
                            "attachment_urls": attachment_urls,
                        },
                    )
                )

            async with self.uow:
                await self.uow.commit()
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback then re-raise (reviewed TD-27-04)
            await self.uow.rollback()
            raise

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
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids and user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.not_participant")

        # RACE-02 Fix: DMs are shared state. Unilateral deletion by a regular
        # participant allows bad actors to delete evidence from the victim's device.
        if user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.deletion_forbidden_non_admin")

        attachment_urls = await self.attachment_service.collect_urls(chat)
        message_count = len(chat.messages)
        attachment_count = len(attachment_urls)

        p_ids = [p.id for p in chat.participants]

        try:
            # RED-04 (audit 2026-03-14): Record ChatDeleted outbox events BEFORE
            # the DELETE commits so ws-hub cache invalidation is durable.
            # StoredEvent rows land in the SAME transaction as the chat deletion —
            # either both succeed or neither does.  OutboxWorker delivers them with
            # at-least-once semantics, closing the 60s BOLA window that existed
            # when invalidation was a best-effort post-commit network call.
            from app.core.events import AttachmentCleanupRequested as _ACR
            from app.core.events import ChatDeleted as ChatDeletedEvent
            from app.models.domain_events import StoredEvent as _StoredEvent

            for _pid in p_ids:
                self.repository.add(
                    _StoredEvent(
                        event_type=ChatDeletedEvent.EVENT_TYPE,
                        aggregate_type="Chat",
                        aggregate_id=str(chat_id),
                        payload={"chat_id": str(chat_id), "participant_id": str(_pid)},
                    )
                )

            # PERF-W10-05: Durable file cleanup alongside ChatDeleted in ONE tx.
            if attachment_urls:
                self.repository.add(
                    _StoredEvent(
                        event_type=_ACR.EVENT_TYPE,
                        aggregate_type="Chat",
                        aggregate_id=str(chat_id),
                        payload={
                            "chat_id": str(chat_id),
                            "attachment_urls": attachment_urls,
                        },
                    )
                )

            await self.repository.delete_chat(chat_id)
            async with self.uow:
                await self.uow.commit()
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback then re-raise (reviewed TD-27-04)
            await self.uow.rollback()
            raise

        # LOW-W19: cache invalidation moved to after commit so that a failure
        # in the invalidation calls does not trigger an erroneous rollback of
        # an already-committed transaction.
        await invalidate_chat_participants_cache(chat_id)
        await invalidate_presence_audience_cache(*p_ids)

        # R-02 (audit 2026-03-08) / RED-04 (audit 2026-03-14):
        # Best-effort immediate invalidation — fast-path that works when ws-hub
        # is healthy.  If this call fails, the ChatDeleted outbox events recorded
        # above guarantee that OutboxWorker will retry until successful.
        from app.services.ws_hub_client import invalidate_ws_hub_cache

        await asyncio.gather(
            *(invalidate_ws_hub_cache(str(_pid), str(chat_id)) for _pid in p_ids),
            return_exceptions=True,  # one failure must not abort the rest
        )

        return ChatMaintenanceResult(
            chat_id=chat_id,
            status="deleted",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )
