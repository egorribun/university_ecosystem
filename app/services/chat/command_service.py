"""Chat message and maintenance commands.

TD-W9-01 (audit 2026-03-16): Chat *creation* logic (Redis DM lock, presence
hydration) lives in ChatCreationService.  This service owns message dispatch
and maintenance operations (mark-read, clear-history, delete-chat).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import (  # TD-23-04 (audit 2026-03-25 Wave 23)
    TYPE_CHECKING,
    Any,
    Never,
    Protocol,
    cast,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import UploadFile

    from app.models import User
    from app.models.chat import Attachment
    from app.repositories.chat_repository import SendReceiptState
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.chat import (
        AttachmentResponse,
        ChatMaintenanceResult,
        MessageResponse,
    )
    from app.schemas.dtos.chat import AttachmentDTO, MessageDTO

    from .notification_service import ChatNotificationService

from fastapi import HTTPException, status
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)
from redis.exceptions import (
    WatchError,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
from app.core.logging import get_logger
from app.models import Message
from app.models.chat import Attachment
from app.models.enums import UserRole
from app.schemas.chat import (
    ChatMaintenanceResult,
    MessageResponse,
    PresenceStatus,
    ReplyPreview,
)

logger = get_logger(__name__)


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


def _make_send_receipt_digest(
    chat_id: uuid.UUID, user_id: uuid.UUID, client_key: str
) -> str:
    """Stable private identity; Redis HMAC rotation must not reset DB ownership."""
    domain = b"university-ecosystem:chat-send-receipt:v1\0"
    return hashlib.sha256(
        domain + chat_id.bytes + user_id.bytes + client_key.encode("utf-8")
    ).hexdigest()


def _is_send_receipt_conflict(
    error: IntegrityError, *, expected_schema: str | None = None
) -> bool:
    """Recover only our named unique constraint, never unrelated integrity errors."""
    current: BaseException | None = error.orig
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        diagnostic = getattr(current, "diag", current)
        sqlstate = getattr(current, "sqlstate", None) or getattr(
            current, "pgcode", None
        )
        if (
            sqlstate == "23505"
            and getattr(diagnostic, "constraint_name", None)
            == "uq_chat_send_receipts_chat_user_key"
        ):
            table = getattr(diagnostic, "table_name", None)
            schema = getattr(diagnostic, "schema_name", None)
            return bool(
                (table is None or table == "chat_send_receipts")
                and (
                    expected_schema is None
                    or schema is None
                    or schema == expected_schema
                )
            )
        current = current.__cause__
    return False


async def _change_idempotency_slot(
    key: str, expected: str, replacement: str | None = None, *, ttl: int = 300
) -> bool:
    """Compare and mutate atomically; an expired owner cannot alter a new lease."""
    from app.deps.cache import get_cache_client

    cache = await get_cache_client()
    while True:
        async with cache.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                current = await pipe.get(key)
                if isinstance(current, bytes):
                    current = current.decode("utf-8")
                if current != expected:
                    return False
                pipe.multi()
                if replacement is None:
                    pipe.delete(key)
                else:
                    pipe.set(key, replacement, ex=ttl)
                await pipe.execute()
                return True
            except WatchError:
                # Re-read ownership after an expiry/replacement during WATCH.
                continue


def _idempotency_in_progress() -> Never:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "idempotency_in_progress",
            "message": "This message is already being processed; retry with the same key",
        },
        headers={"Retry-After": "1"},
    )


if TYPE_CHECKING:
    from fastapi import UploadFile


class AttachmentProcessorProtocol(Protocol):
    async def process_upload(
        self, upload: UploadFile, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]: ...  # pragma: no branch
    async def cleanup_files(self, urls: list[str]) -> None: ...  # pragma: no branch
    async def copy_for_forward(
        self, attachment: AttachmentDTO, chat_id: uuid.UUID, *, locale: str | None
    ) -> dict[str, str | int]: ...  # pragma: no branch
    async def collect_urls(
        self, chat: Any
    ) -> list[str]: ...  # pragma: no branch  # Any: accepts Chat or ChatDTO


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

    async def _cleanup_unreferenced_uploaded_files(self, urls: list[str]) -> None:
        """Delete failed-transaction files only when no Attachment owns their URL.

        A database can commit while its acknowledgement is lost. A later rollback
        cannot undo committed rows, so check the primary session after rollback.
        Keep every object if that ownership check cannot be completed.
        """
        candidates = list(dict.fromkeys(url for url in urls if url))
        if not candidates:
            return
        try:
            result = await self.session.execute(
                select(Attachment.url).where(Attachment.url.in_(candidates)).distinct()
            )
            referenced = set(result.scalars().all())
        except (SQLAlchemyError, ConnectionError, OSError):  # RZ-22-01
            # Retain the objects if attachment ownership cannot be checked.
            logger.warning("chat_attachment_reference_check_failed")
            return
        unreferenced = [url for url in candidates if url not in referenced]
        if unreferenced:
            await self.attachment_service.cleanup_files(unreferenced)

    async def _send_receipt_response(
        self,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        receipt: SendReceiptState,
    ) -> MessageResponse:
        """Hydrate only the authorized chat; deletion never permits resurrection."""
        if receipt.message_id is None:
            _idempotency_in_progress()
        message = await self.repository.get_message_by_id(
            receipt.message_id, user_id=user_id, chat_id=chat_id
        )
        if message is None:
            _idempotency_in_progress()
        return MessageResponse(
            **message.model_dump(exclude={"replied_to"}),
            reply_to=ReplyPreview.from_message(message.replied_to),
            sender_presence=PresenceStatus(
                active=ws_manager.is_online(message.sender_id)
            ),
        )

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

        The Idempotency-Key is scoped to (chat_id, user_id). A completed primary
        DB receipt replays the original message within a fixed 24-hour window.
        Current membership is required before any replay. A live uncommitted
        Redis lease returns HTTP 409 with Retry-After; retry the same key later.
        Redis admission is only an optimization. Historical cache-only sends
        and mixed old/new writers are outside the durable replay guarantee.
        """
        _idempotency_cache_key: str | None = None
        _pending_value: str | None = None
        _receipt_digest: str | None = None
        _receipt_expires_at: datetime | None = None
        # Rollback expires ORM attributes even when expire_on_commit is disabled.
        user_id = user.id

        # Check existence first (for correct 404 reporting)
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        # Check participation (TD-4 security audit)
        is_participant = await self.repository.check_participant(chat_id, user_id)
        if not is_participant:
            raise_forbidden(locale, "errors.chat.not_participant")

        # Current membership is required even for a completed retry. Consult
        # primary ownership before Redis so a committed response survives cache
        # outage, lost completion, eviction, or rotation of the cache HMAC key.
        if idempotency_key:
            from app.deps.cache import get_cache_client

            _receipt_digest = _make_send_receipt_digest(
                chat_id, user_id, idempotency_key
            )
            receipt = await self.repository.get_send_receipt(
                chat_id, user_id, _receipt_digest
            )
            if receipt is not None and receipt.expires_at > receipt.observed_at:
                return await self._send_receipt_response(chat_id, user_id, receipt)

            _cache = await get_cache_client()
            _idempotency_cache_key = _make_idempotency_key(
                chat_id, user_id, idempotency_key
            )
            _cached = await _cache.get(_idempotency_cache_key)
            if _cached:
                try:
                    _hit = json.loads(_cached)
                    _msg_id = uuid.UUID(_hit["message_id"])
                except (ValueError, KeyError, TypeError):  # RZ-28-01
                    # Pending or malformed values are not ownership grants.
                    pass
                else:
                    if receipt is not None or "receipt_version" in _hit:
                        # An expired DB receipt overrides even a legacy cache
                        # value. New-format values without a live DB receipt
                        # cannot resurrect a completed window after cleanup.
                        cached_text = (
                            _cached.decode("utf-8")
                            if isinstance(_cached, bytes)
                            else _cached
                        )
                        await _change_idempotency_slot(
                            _idempotency_cache_key, cached_text
                        )
                    else:
                        # Bounded compatibility for pre-receipt deployments.
                        # There is no historical key mapping to backfill safely.
                        _full = await self.repository.get_message_by_id(
                            _msg_id, user_id=user_id, chat_id=chat_id
                        )
                        if _full is not None:
                            return MessageResponse(
                                **_full.model_dump(exclude={"replied_to"}),
                                reply_to=ReplyPreview.from_message(_full.replied_to),
                                sender_presence=PresenceStatus(
                                    active=ws_manager.is_online(_full.sender_id)
                                ),
                            )

        # Wave 207 — if this is a reply, the target must exist AND be in THIS chat.
        # message_exists_in_chat checks both (id == … AND chat_id == …) via EXISTS,
        # so a reply to a message in another chat — or a bogus id — 404s before any
        # DB write. The 404-before-insert also avoids a mid-transaction FK error on
        # the SET NULL self-FK.
        if reply_to_message_id is not None:
            target_in_chat = await self.repository.message_exists_in_chat(
                reply_to_message_id, chat_id, user_id=user_id
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

        # Reserve before uploads. A losing request returns a retryable conflict;
        # only the owner may write or release/promote the scoped client key.
        if _idempotency_cache_key:
            _pending_value = json.dumps(
                {"status": "pending", "owner": uuid.uuid4().hex}
            )
            acquired = await _cache.set(
                _idempotency_cache_key, _pending_value, nx=True, ex=300
            )
            if not acquired:
                _idempotency_in_progress()

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
                except ExceptionGroup as upload_errors:
                    # TaskGroup groups failures from its workers. Restore the
                    # normal client-error contract only when every leaf is a
                    # known HTTPException; mixed/internal failures must remain
                    # grouped so an upload rejection cannot hide a real defect.
                    leaves: list[BaseException] = []
                    # Use a LIFO stack while preserving the original first-leaf order.
                    pending: list[BaseException] = list(
                        reversed(upload_errors.exceptions)
                    )
                    while pending:
                        error = pending.pop()
                        if isinstance(error, ExceptionGroup):
                            pending.extend(reversed(error.exceptions))
                        else:
                            leaves.append(error)

                    if leaves and all(
                        isinstance(error, TimeoutError) for error in leaves
                    ):
                        raise_validation_error("errors.files.upload_timeout", locale)
                    if leaves and all(
                        isinstance(error, HTTPException) for error in leaves
                    ):
                        raise cast(HTTPException, leaves[0]) from None
                    raise

        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — cleans up partial uploads then re-raises (reviewed TD-27-04)
            # Phase 1 failure: clean up any partial uploads and release slot.
            if saved_urls:
                await self.attachment_service.cleanup_files(saved_urls)
            if _idempotency_cache_key and _pending_value:
                await _change_idempotency_slot(_idempotency_cache_key, _pending_value)
            raise

        # ── Phase 2: Atomic DB write ─────────────────────────────────────────
        # All uploads succeeded — now write Message + Attachments + MessageSent
        # event in a single transaction. If commit has begun and its outcome is
        # unknown, keep the bounded pending lease so an immediate retry cannot
        # create a duplicate message.
        commit_attempted = False
        message_event_emitter: EventEmitterMixin | None = None
        try:
            if _idempotency_cache_key and _pending_value:
                # Uploads may outlive the lease. Verify and renew ownership before
                # entering the DB mutation, so an old uploader cannot insert.
                if not await _change_idempotency_slot(
                    _idempotency_cache_key, _pending_value, _pending_value
                ):
                    _idempotency_in_progress()
            message = Message(
                chat_id=chat_id,
                sender_id=user_id,
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
            message_event_emitter = cast(EventEmitterMixin, message)
            message_event_emitter.record_event(
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

            if _receipt_digest is not None:
                # Adjudicate receipt ownership before the Chat timestamp UPDATE.
                # The exact unique conflict rolls back Message, attachments and
                # MessageSent together; no losing write is committed.
                # Claim the exact key before opportunistic cleanup, otherwise
                # different-key retries can wait on each other's pruned rows.
                _receipt_expires_at = await self.repository.create_send_receipt(
                    chat_id, user_id, _receipt_digest, message.id
                )
                await self.repository.prune_expired_send_receipts(chat_id, user_id)

            # The UPDATE below triggers an SQLAlchemy autoflush — at that point
            # `message` (and its _pending_domain_events) are still in session.new,
            # so capture_domain_events() correctly creates the StoredEvent row and
            # adds it to the session.  Both Message and StoredEvent are committed
            # atomically in the uow.commit() call below.
            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))

            # DI supplies a UOW bound to the request-owned session. Commit it
            # directly so a failing context-manager rollback cannot replace the
            # commit error before this method performs its one guarded rollback.
            commit_attempted = True
            await self.uow.commit()

        except (
            Exception,
            asyncio.CancelledError,
        ) as error:  # RZ-22-01-JUSTIFIED: rollback and cleanup before propagating failure or cancellation
            # RACE-BE-01: Phase 2 failed — rollback first, then preserve any file
            # that a possibly committed Attachment row still references.
            rollback_succeeded = True
            try:
                await self.uow.rollback()
            except (
                Exception
            ):  # RZ-22-01-JUSTIFIED: preserve failure; retain files on rollback error
                rollback_succeeded = False
                logger.warning("chat_message_rollback_failed")
            if rollback_succeeded and message_event_emitter is not None:
                # A failed receipt INSERT may precede event capture. Do not let
                # this rolled-back send emit MessageSent on a reused session.
                message_event_emitter.clear_events()
            receipt_conflict = False
            if (
                rollback_succeeded
                and _receipt_digest is not None
                and isinstance(error, IntegrityError)
            ):
                schema = getattr(
                    self.session.get_bind().dialect, "default_schema_name", None
                )
                receipt_conflict = _is_send_receipt_conflict(
                    error, expected_schema=schema if isinstance(schema, str) else None
                )
                if receipt_conflict:
                    # Rollback clears transaction-local identity. Tenant scope is
                    # restored by the existing after_begin session listener.
                    await self.repository.set_message_rls_user(user_id)
            if saved_urls and rollback_succeeded:
                try:
                    await self._cleanup_unreferenced_uploaded_files(saved_urls)
                except Exception:  # RZ-22-01-JUSTIFIED: best-effort cleanup must preserve the transaction failure
                    logger.warning("chat_message_attachment_cleanup_failed")
            if _idempotency_cache_key and _pending_value:
                try:
                    if commit_attempted:
                        # Compare-and-renew only our still-live lease. If commit
                        # acknowledgement was lost, this blocks immediate retries
                        # for one bounded TTL without claiming durable idempotency.
                        await _change_idempotency_slot(
                            _idempotency_cache_key, _pending_value, _pending_value
                        )
                    else:
                        await _change_idempotency_slot(
                            _idempotency_cache_key, _pending_value
                        )
                except Exception:  # RZ-22-01-JUSTIFIED: cache cleanup must preserve the transaction failure
                    logger.warning("chat_message_idempotency_cleanup_failed")
            if receipt_conflict and _receipt_digest is not None:
                # Do not access the potentially expired User ORM object.
                current_chat = await self.repository.get_by_id(chat_id)
                ensure_exists(current_chat, "chat", locale)
                if not await self.repository.check_participant(chat_id, user_id):
                    raise_forbidden(locale, "errors.chat.not_participant")
                winner = await self.repository.get_send_receipt(
                    chat_id, user_id, _receipt_digest
                )
                if winner is not None and winner.expires_at > winner.observed_at:
                    return await self._send_receipt_response(chat_id, user_id, winner)
                _idempotency_in_progress()
            raise

        # Cache is only a hint. Its TTL must not extend the fixed DB window,
        # including the time already spent waiting for COMMIT acknowledgement.
        if (
            _idempotency_cache_key
            and _pending_value
            and _receipt_expires_at is not None
        ):
            remaining = await self.repository.send_receipt_remaining_seconds(
                _receipt_expires_at
            )
            try:
                if remaining:
                    await _change_idempotency_slot(
                        _idempotency_cache_key,
                        _pending_value,
                        json.dumps(
                            {
                                "status": "completed",
                                "receipt_version": 1,
                                "message_id": str(message.id),
                                "expires_at": _receipt_expires_at.isoformat(),
                            }
                        ),
                        ttl=min(remaining, 86400),
                    )
                else:
                    await _change_idempotency_slot(
                        _idempotency_cache_key, _pending_value
                    )
            except (RedisConnectionError, RedisTimeoutError, OSError):
                # A committed receipt replays even if completion remains pending.
                logger.warning("chat_message_idempotency_completion_failed")

        # Reload message with attachments for the response
        reloaded = await self.repository.get_last_messages(
            [message.id], user_id=user_id
        )
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
                forwarded_from_name=message.forwarded_from_name,  # Wave 211 — W203 SW8
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

        return msg_data

    async def forward_messages(
        self,
        dest_chat_id: uuid.UUID,
        user: User,
        source_chat_id: uuid.UUID,
        message_ids: list[uuid.UUID],
        locale: str,
    ) -> list[MessageResponse]:
        """Forward 1..N messages from a source chat into a destination chat (Wave 211).

        Snapshot-copy model: each source message's content + attachments are COPIED
        into a fresh message in the destination chat, plus a denormalized
        ``forwarded_from_name`` "Forwarded from X" label. The source is NEVER
        dereferenced cross-chat to render content — the forward is self-contained,
        so a destination viewer with no rights in the source chat cannot see source
        content. Reactions are NOT copied (they belong to the source's context).

        Authorization is authz-first (W209 discipline):
          1. dest exists + actor is a dest participant (can send here) — 404/403;
          2. actor is a SOURCE participant (can read there) — 403 BEFORE any source
             read, so a non-participant never learns whether a source id exists
             (the cross-chat-leak gate);
          3. each id belongs to the source chat — 404, validated for ALL ids before
             any message is created (all-or-nothing, mirroring the W207 reply
             404-before-insert, looped).

        All N forwards + their attachment copies are written in ONE transaction; each
        emits ``MessageSent`` so the existing outbox → broadcast (W204) → notification
        (W210 group context) rail fans them out unchanged.
        """
        # Dedupe while preserving order (a client could repeat an id).
        ordered_ids = list(dict.fromkeys(message_ids))

        # 1) DEST existence + participant (send-side) — authz-first.
        dest_chat = await self.repository.get_by_id(dest_chat_id)
        ensure_exists(dest_chat, "chat", locale)
        assert dest_chat is not None  # noqa: S101
        if not await self.repository.check_participant(dest_chat_id, user.id):
            raise_forbidden(locale, "errors.chat.not_participant")

        # 2) SOURCE participant (read-side) — the cross-chat-leak gate. Checked
        #    BEFORE any source message is read, so forwarding FROM a chat the actor
        #    is not in returns 403 without revealing whether any source id exists.
        if not await self.repository.check_participant(source_chat_id, user.id):
            raise_forbidden(locale, "errors.chat.not_participant")

        # 3) Each id must belong to the source chat — validate ALL before creating
        #    ANY message (all-or-nothing). message_exists_in_chat is one EXISTS/id.
        for mid in ordered_ids:
            if not await self.repository.message_exists_in_chat(
                mid, source_chat_id, user_id=user.id
            ):
                raise_not_found("message", locale)

        # Load only live sources; a tombstone must not be forwarded with its
        # retained attachment references. The DTO guard also fails closed if a
        # repository implementation returns a tombstone despite the SQL filter.
        sources = await self.repository.get_last_messages(
            ordered_ids, user_id=user.id, live_only=True
        )
        if len(sources) != len(ordered_ids) or any(
            source.deleted_at is not None for source in sources.values()
        ):
            # Defensive TOCTOU guard — message_exists_in_chat validated each id
            # above, then this live-only batch prevents a stale tombstone from
            # reaching attachment copying or destination writes.
            raise_not_found("message", locale)

        # Resolve the ORIGINAL senders' display names for the "Forwarded from X"
        # label. full_name lives on UserProfile, NOT the bare User selectinload'd
        # into MessageDTO.sender (which yields full_name=None — the W207 SW5
        # gotcha), so resolve it via a profile-loaded lookup. Batched: ONE SELECT
        # for all distinct source senders, never an N+1.
        sender_names = await self.repository.get_user_display_names(
            list({src.sender_id for src in sources.values()})
        )

        # A forwarded message must own its own object. Sharing the source URL
        # lets source-chat cleanup delete the destination's live attachment.
        total_size = sum(
            attachment.size
            for mid in ordered_ids
            for attachment in sources[mid].attachments
        )
        if total_size > settings.chat_attachment_max_total_bytes:
            raise_validation_error("errors.files.total_size_exceeded", locale)

        copied: dict[uuid.UUID, list[dict[str, str | int]]] = {}
        copied_urls: list[str] = []
        now = datetime.now(UTC)
        created: list[Message] = []
        try:
            for mid in ordered_ids:
                copied[mid] = []
                for attachment in sources[mid].attachments:
                    metadata = await self.attachment_service.copy_for_forward(
                        attachment, dest_chat_id, locale=locale
                    )
                    copied_urls.append(str(metadata["url"]))
                    copied[mid].append(metadata)

            for mid in ordered_ids:
                src = sources[mid]
                message = Message(
                    chat_id=dest_chat_id,
                    sender_id=user.id,
                    content=src.content,
                    # Snapshot the ORIGINAL sender's name (the only forwarded-from datum
                    # the FE renders), resolved via the profile-loaded batch above. The
                    # audit-only *_id columns record provenance but are never serialized
                    # / dereferenced cross-chat (privacy).
                    forwarded_from_name=sender_names.get(src.sender_id),
                    forwarded_from_chat_id=source_chat_id,
                    forwarded_from_message_id=src.id,
                )
                await self.repository.create_message(message)
                # Record the event right after the flush (see send_message ARCH-BE-01 /
                # W205 SW-A): central capture tracks the emitter on session.info, so the
                # outbox lands regardless of later autoflush ordering. sender = the
                # FORWARDER, chat = the DEST — a forward is a normal new message.
                message.record_event(
                    MessageSent(
                        message_id=message.id,
                        chat_id=message.chat_id,
                        sender_id=message.sender_id,
                        content_preview=message.content[:50],
                    )
                )
                for metadata in copied[mid]:
                    self.repository.add(
                        Attachment(
                            message=message,
                            url=str(metadata["url"]),
                            file_type=str(metadata["file_type"]),
                            filename=str(metadata["filename"]),
                            size=int(metadata["size"]),
                        )
                    )
                created.append(message)

            # One timestamp bump and one atomic commit for all N messages.
            await self.repository.update_timestamp_by_id(dest_chat_id, now)
            # The injected UOW borrows the request session; the catch below
            # owns rollback and must see the original commit exception.
            await self.uow.commit()
        except (
            Exception,
            asyncio.CancelledError,
        ):  # RZ-22-01-JUSTIFIED: attempt transaction and copied-file rollback before re-raising failure or cancellation
            rollback_succeeded = True
            try:
                await self.uow.rollback()
            except Exception:  # RZ-22-01-JUSTIFIED: preserve original failure and retain files when rollback fails
                rollback_succeeded = False
                logger.warning("chat_forward_rollback_failed")
            if copied_urls and rollback_succeeded:
                try:
                    await self._cleanup_unreferenced_uploaded_files(copied_urls)
                except Exception:  # RZ-22-01-JUSTIFIED: best-effort file cleanup must not mask original failure
                    logger.warning("chat_forward_copy_cleanup_failed")
            raise

        # Reload all created messages (attachments selectinload'd) for the response,
        # preserving source order. forwarded_from_name auto-carries via model_dump;
        # a forward is not a reply → reply_to=None. message.id is the identity-map
        # PK (not expired on commit), so the reload-by-id is safe.
        reloaded = await self.repository.get_last_messages(
            [m.id for m in created], user_id=user.id
        )
        responses: list[MessageResponse] = []
        for message in created:
            presence = PresenceStatus(active=ws_manager.is_online(user.id))
            full = reloaded.get(message.id)
            if full is not None:
                responses.append(
                    MessageResponse(
                        **full.model_dump(exclude={"replied_to"}),
                        reply_to=None,
                        sender_presence=presence,
                    )
                )
            else:
                # Degraded rare path (reload returned nothing) — refresh the expired
                # ORM object before reading scalar columns (mirrors send_message).
                await self.session.refresh(message)
                responses.append(
                    MessageResponse(
                        id=message.id,
                        chat_id=message.chat_id,
                        sender_id=message.sender_id,
                        content=message.content,
                        created_at=message.created_at,
                        read_status=message.read_status,
                        edited_at=message.edited_at,
                        deleted_at=message.deleted_at,
                        forwarded_from_name=message.forwarded_from_name,
                        sender_presence=presence,
                        reply_to=None,
                    )
                )
        return responses


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

    _MESSAGE_PAGE_SIZE = 512
    _ATTACHMENT_EVENT_URL_BATCH_SIZE = 128

    async def _message_pages(
        self, chat_id: uuid.UUID, user_id: uuid.UUID
    ) -> AsyncIterator[list[MessageDTO]]:
        """Yield bounded, locked message pages using their self-contained cursor.

        The cursor embeds the final message's timestamp and ID, so deleting that
        page does not invalidate the next keyset query. Message rows are locked
        before their attachments are loaded to serialize FK inserts with cleanup.
        """
        cursor: str | None = None
        while True:
            messages, has_more, next_cursor = await self.repository.get_messages(
                chat_id,
                cursor,
                self._MESSAGE_PAGE_SIZE,
                user_id=user_id,
                for_update=True,
            )
            if not messages:
                if has_more:
                    raise RuntimeError("chat maintenance page returned no cursor rows")
                return

            yield messages
            if not has_more:
                return
            if next_cursor is None:
                raise RuntimeError("chat maintenance page omitted its next cursor")
            cursor = next_cursor

    def _stage_attachment_cleanup_events(
        self, chat_id: uuid.UUID, urls: list[str]
    ) -> None:
        if not urls:
            return

        from app.core.events import AttachmentCleanupRequested as _ACR
        from app.models.domain_events import StoredEvent as _StoredEvent

        for start in range(0, len(urls), self._ATTACHMENT_EVENT_URL_BATCH_SIZE):
            url_batch = urls[start : start + self._ATTACHMENT_EVENT_URL_BATCH_SIZE]
            self.repository.add(
                _StoredEvent(
                    event_type=_ACR.EVENT_TYPE,
                    aggregate_type="Chat",
                    aggregate_id=str(chat_id),
                    payload={"chat_id": str(chat_id), "attachment_urls": url_batch},
                )
            )

    @staticmethod
    def _page_attachment_urls(messages: list[MessageDTO]) -> list[str]:
        return [
            attachment.url
            for message in messages
            for attachment in message.attachments
            if attachment.url
        ]

    async def mark_read(self, chat_id: uuid.UUID, user: User, locale: str) -> None:
        """Mark all messages in a chat as read by the user."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        # Wave 210 G2 — pass chat_type so groups mark-read via the per-recipient
        # ChatReadReceipt high-water-mark (DMs keep Message.read_status).
        read_at, affected = await self.repository.mark_messages_read(
            chat_id, user.id, chat.chat_type
        )
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
        """Edit a message's content (author-only) and queue durable delivery.

        The transactional outbox records the event with the row mutation; its
        handler broadcasts only after the commit succeeds.
        The repo's author-only WHERE means affected == 0 ⇒ not the author / missing /
        already deleted ⇒ 404 (raised before commit; nothing to persist).
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        _, affected = await self.repository.edit_message(
            message_id, user.id, new_content, chat_id=chat_id
        )
        if affected == 0:
            raise_not_found("message", locale)

        async with self.uow:
            await self.uow.commit()

    async def soft_delete_message(
        self,
        chat_id: uuid.UUID,
        message_id: uuid.UUID,
        user: User,
        locale: str,
    ) -> None:
        """Soft-delete a message (author-only) and queue durable delivery.

        The transactional outbox records the event with the tombstone mutation; its
        handler broadcasts only after the commit succeeds. The repo clears content
        and stamps deleted_at (D1 tombstone); affected == 0 ⇒ 404.
        """
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        _, affected = await self.repository.soft_delete_message(
            message_id, user.id, chat_id=chat_id
        )
        if affected == 0:
            raise_not_found("message", locale)

        async with self.uow:
            await self.uow.commit()

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

        if not await self.repository.message_exists_in_chat(
            message_id, chat_id, user_id=user.id
        ):
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

        if not await self.repository.message_exists_in_chat(
            message_id, chat_id, user_id=user.id
        ):
            return

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
        removal_event_id: uuid.UUID | None = None
        if affected:
            from app.core.events import (
                ChatParticipantRemoved as _ChatParticipantRemoved,
            )
            from app.models.domain_events import StoredEvent as _StoredEvent
            from app.utils.uuid_v7 import generate_uuid7 as _generate_uuid7

            removal_event_id = _generate_uuid7()
            self.repository.add(
                _StoredEvent(
                    id=removal_event_id,
                    event_type=_ChatParticipantRemoved.EVENT_TYPE,
                    aggregate_type="Chat",
                    aggregate_id=str(chat_id),
                    payload={
                        "chat_id": str(chat_id),
                        "user_id": str(target_user_id),
                    },
                )
            )
        async with self.uow:
            await self.uow.commit()

        if affected:
            cache_results = await asyncio.gather(
                invalidate_chat_participants_cache(chat_id),
                invalidate_presence_audience_cache(target_user_id, *participant_ids),
                return_exceptions=True,
            )

            # The transactionally stored event remains the durable retry path.
            # Publish the same event identity now for low-latency room eviction;
            # JetStream deduplicates the outbox retry, and the hub also treats a
            # repeated eviction as idempotent after refreshing membership.
            from app.services.ws_hub_client import invalidate_ws_hub_cache

            await asyncio.gather(
                invalidate_ws_hub_cache(
                    str(target_user_id),
                    str(chat_id),
                    evict_room=True,
                    event_id=str(removal_event_id),
                ),
                return_exceptions=True,
            )
            # A cache failure must not prevent the independent room-revocation
            # fast path. Preserve the existing error contract after all
            # post-commit effects have had a chance to run; the stored event
            # remains available for durable WS-hub retry.
            for cache_result in cache_results:
                if isinstance(cache_result, BaseException):
                    raise cache_result

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
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids and user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.not_participant")

        # RACE-02 Fix: DMs are shared state. Unilateral history destruction by a regular
        # participant allows bad actors to delete evidence from the victim's device.
        if user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.history_clear_forbidden_non_admin")

        try:
            locked_chat = await self.repository.get_orm_for_update(chat_id)
            ensure_exists(locked_chat, "chat", locale)
            assert locked_chat is not None  # noqa: S101

            locked_participant_ids = (
                await self.repository.lock_participant_ids_for_maintenance(chat_id)
            )
            if not locked_participant_ids:
                raise_forbidden(locale, "errors.chat.not_participant")
            locked_participant_set = set(locked_participant_ids)
            # Only administrators reach this branch. Select a current participant
            # solely as the transaction-local RLS identity after membership locks.
            rls_user_id = (
                user.id
                if user.id in locked_participant_set
                else locked_participant_ids[0]
            )

            message_count = 0
            attachment_count = 0
            async for messages in self._message_pages(chat_id, rls_user_id):
                attachment_urls = self._page_attachment_urls(messages)
                attachment_count += len(attachment_urls)
                message_count += await self.repository.delete_messages(
                    [message.id for message in messages],
                    chat_id=chat_id,
                    user_id=rls_user_id,
                )
                self._stage_attachment_cleanup_events(chat_id, attachment_urls)
                # Flush each bounded page to keep pending ORM state bounded while
                # retaining one transaction for deletes and durable cleanup events.
                await self.uow.flush()

            await self.repository.update_timestamp_by_id(chat_id, datetime.now(UTC))

            # Commit directly; the injected UOW borrows the request session and
            # this handler owns rollback for failures and cancellation.
            await self.uow.commit()
        except BaseException:  # RZ-22-01-JUSTIFIED: rollback cleanup before re-raise
            # A rollback error must not replace the original operation failure.
            # Leave a new CancelledError uncaught so cancellation still propagates.
            try:
                await self.uow.rollback()
            except Exception:  # RZ-22-01-JUSTIFIED: cleanup preserves original failure
                logger.warning("chat_clear_history_rollback_failed")
            raise

        return ChatMaintenanceResult(
            chat_id=chat_id,
            status="cleared",
            deleted_messages=message_count,
            deleted_attachments=attachment_count,
        )

    async def delete_chat(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatMaintenanceResult:
        """Permanently delete a chat."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids and user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.not_participant")

        # RACE-02 Fix: DMs are shared state. Unilateral deletion by a regular
        # participant allows bad actors to delete evidence from the victim's device.
        if user.role != UserRole.ADMIN:
            raise_forbidden(locale, "errors.chat.deletion_forbidden_non_admin")

        try:
            locked_chat = await self.repository.get_orm_for_update(chat_id)
            ensure_exists(locked_chat, "chat", locale)
            assert locked_chat is not None  # noqa: S101

            p_ids = await self.repository.lock_participant_ids_for_maintenance(chat_id)
            if not p_ids:
                raise_forbidden(locale, "errors.chat.not_participant")
            p_id_set = set(p_ids)
            # Only administrators reach this branch. Select a current participant
            # solely as the transaction-local RLS identity after membership locks.
            rls_user_id = user.id if user.id in p_id_set else p_ids[0]

            # RED-04 (audit 2026-03-14): Record ChatDeleted outbox events BEFORE
            # the DELETE commits so ws-hub cache invalidation is durable.
            # StoredEvent rows land in the SAME transaction as the chat deletion —
            # either both succeed or neither does.  OutboxWorker delivers them with
            # at-least-once semantics, closing the 60s BOLA window that existed
            # when invalidation was a best-effort post-commit network call.
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

            message_count = 0
            attachment_count = 0
            async for messages in self._message_pages(chat_id, rls_user_id):
                attachment_urls = self._page_attachment_urls(messages)
                message_count += len(messages)
                attachment_count += len(attachment_urls)
                self._stage_attachment_cleanup_events(chat_id, attachment_urls)
                await self.uow.flush()

            await self.repository.delete_chat(chat_id)
            # Commit directly; the injected UOW borrows the request session and
            # this handler owns rollback for failures and cancellation.
            await self.uow.commit()
        except BaseException:  # RZ-22-01-JUSTIFIED: rollback cleanup before re-raise
            # A rollback error must not replace the original operation failure.
            # Leave a new CancelledError uncaught so cancellation still propagates.
            try:
                await self.uow.rollback()
            except Exception:  # RZ-22-01-JUSTIFIED: cleanup preserves original failure
                logger.warning("chat_delete_rollback_failed")
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
