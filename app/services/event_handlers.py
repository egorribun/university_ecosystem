"""
Domain event handlers.

Contains handler implementations for domain events.
These handlers are registered with the EventBus during application startup.
"""

from __future__ import annotations

import math
from typing import cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.core.config import settings
from app.core.database import async_session
from app.core.events import (
    AttachmentCleanupRequested,
    ChatDeleted,
    ChatParticipantRemoved,
    DomainEvent,
    DurableEventDeferred,
    EventCreated,
    EventRegistration,
    EventUpdated,
    MessageDeleted,
    MessageEdited,
    MessageSent,
    MfaEmailDeliveryRequested,
    MfaEnabled,
    NewsCreated,
    NewsUpdated,
    NotificationSent,
    NotificationsRequested,
    ScheduleDeleted,
    ScheduleUpdated,
    UserCreated,
    UserLoggedIn,
    event_bus,
)
from app.core.logging import get_logger
from app.models.chat import chat_participants
from app.services import search_indexer
from app.services.vector_service import VectorService

logger = get_logger(__name__)


async def log_all_events(event: DomainEvent) -> None:
    """Log all domain events for audit/debugging."""
    logger.info(
        "Domain event: %s (id=%s)",
        event.event_type,
        event.event_id,
    )


async def handle_user_created(event: UserCreated) -> None:
    """Handle user creation events."""
    logger.info(
        "New user registered: user_id=%d",
        event.user_id,
    )
    # Could trigger:
    # - Welcome email
    # - Analytics tracking
    # - Onboarding workflow


async def handle_user_logged_in(event: UserLoggedIn) -> None:
    """Handle successful login events."""
    logger.debug(
        "User login: user_id=%d, ip=%s",
        event.user_id,
        event.ip_address or "unknown",
    )
    # Could trigger:
    # - Session activity metrics
    # - Security anomaly detection


async def handle_mfa_enabled(event: MfaEnabled) -> None:
    """Handle MFA enablement events."""
    logger.info(
        "MFA enabled: user_id=%d, method=%s",
        event.user_id,
        event.method,
    )
    # Could trigger:
    # - Security notification to user
    # - Compliance audit logging


async def handle_mfa_email_delivery_requested(
    event: MfaEmailDeliveryRequested,
) -> None:
    """Decrypt and send one leased MFA envelope; failures remain retryable."""
    if event.delivery_id is None:
        raise ValueError("MFA delivery event is missing delivery_id")
    from uuid import UUID

    from app.auth.mfa.email_otp import (
        MfaDeliveryError,
        SmtpMfaEmailSender,
        build_configured_email_delivery_service,
    )

    try:
        async with async_session() as db:
            service = build_configured_email_delivery_service()
            await service.deliver(
                db,
                delivery_id=UUID(str(event.delivery_id)),
                sender=SmtpMfaEmailSender(),
            )
            await db.commit()
    except DurableEventDeferred:
        raise
    except (
        Exception
    ):  # RZ-22-01-JUSTIFIED: sanitize SMTP/database failure before durable outbox retry
        # Third-party exception text can include the recipient or SMTP banner.
        # The outbox owns retry and DLQ; never persist that text in last_error.
        raise MfaDeliveryError() from None


async def handle_event_created(event: EventCreated) -> None:
    """Handle event creation events."""
    logger.info(
        "Event created: event_id=%s, organizer=%s, title=%s",
        event.event_id_entity,
        event.organizer_id,
        event.title,
    )
    # Could trigger:
    # - Notification to followers
    # - Analytics tracking


async def handle_event_registration(event: EventRegistration) -> None:
    """Handle event registration events."""
    logger.debug(
        "Event registration: event_id=%d, user_id=%d",
        event.event_id_entity,
        event.user_id,
    )
    # Could trigger:
    # - Confirmation email
    # - Calendar invite
    # - Cache invalidation for event stats


async def handle_notification_sent(event: NotificationSent) -> None:
    """Handle notification sent events."""
    logger.debug(
        "Notification sent: notification_id=%s, user_id=%d, type=%s",
        event.notification_id,
        event.user_id,
        event.notification_type,
    )
    # Could trigger:
    # - Delivery tracking
    # - Analytics


def _content_entity_id(value: UUID | str | None) -> UUID | None:
    """Stored outbox payloads encode UUIDs as strings."""
    return UUID(value) if isinstance(value, str) else value


def _usable_content_embedding(embedding: list[float]) -> bool:
    if (
        embedding
        and all(math.isfinite(value) for value in embedding)
        and any(embedding)
    ):
        return True
    if not settings.semantic_search_enabled or not settings.embedding_api_key:
        # An intentionally disabled provider has no projection to update.
        return False
    # The query API can degrade to a zero vector; a durable projection must retry
    # an active provider failure instead of storing a zero/NaN-producing embedding.
    raise RuntimeError(
        "Embedding projection failed: provider returned no usable vector"
    )


async def generate_event_embedding(event: EventCreated | EventUpdated) -> None:
    """Generate embedding for newly created event."""
    async with async_session() as db:
        # An event handler runs outside any request scope and opens its own
        # session, so it constructs the service over that session directly.
        vector_service = VectorService(db=db)
        try:
            # Fetch the event to get full content
            event_id = _content_entity_id(event.event_id_entity)
            db_event = await db.get(models.Event, event_id)
            if not db_event:
                return

            text_to_embed = f"{db_event.title} {db_event.description or ''} {db_event.location or ''}"
            embedding = await vector_service.get_embedding(text_to_embed)
            if not _usable_content_embedding(embedding):
                return
            db_event.embedding = embedding
            await db.commit()
        finally:
            await vector_service.close()


async def generate_news_embedding(event: NewsCreated | NewsUpdated) -> None:
    """Generate embedding for newly created news."""
    async with async_session() as db:
        vector_service = VectorService(db=db)
        try:
            news_id = _content_entity_id(event.news_id)
            db_news = await db.get(models.News, news_id)
            if not db_news:
                return

            text_to_embed = f"{db_news.title} {db_news.content}"
            embedding = await vector_service.get_embedding(text_to_embed)
            if not _usable_content_embedding(embedding):
                return
            db_news.embedding = embedding
            await db.commit()
        finally:
            await vector_service.close()


async def index_news_for_search(event: NewsCreated | NewsUpdated) -> None:
    """Make a created/updated news article findable through ``/api/v1/search``."""
    await search_indexer.index_news(event.news_id)


async def index_event_for_search(event: EventCreated | EventUpdated) -> None:
    """Make a created/updated event findable (deactivated events are removed)."""
    await search_indexer.index_event(event.event_id_entity)


async def _set_message_rls_identity(db: AsyncSession, chat_id: UUID) -> UUID | None:
    """Set a transaction-local messages RLS identity from live chat membership.

    Event payloads intentionally contain identifiers only. Select an identity
    from the non-RLS association table before touching ``messages``; a removed
    or empty chat has no identity and must not fall back to a privileged read.
    """
    member_result = await db.execute(
        select(chat_participants.c.user_id)
        .where(chat_participants.c.chat_id == chat_id)
        .order_by(chat_participants.c.user_id)
        .limit(1)
    )
    member_id = cast(UUID | None, member_result.scalar_one_or_none())
    if member_id is None:
        return None

    if db.get_bind().dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(member_id)},
        )
    return member_id


async def handle_message_sent(event: MessageSent) -> None:
    """
    Handle message sent events by triggering notifications.
    (RZ-F-11 Outbox Pattern implementation)
    """
    if event.message_id is None or event.chat_id is None:
        logger.error("Message sent event is missing its identifiers")
        return

    from app.repositories.chat_repository import ChatRepository
    from app.services.chat.notification_service import ChatNotificationService

    async with async_session() as db:
        repo = ChatRepository(db)

        # Messages use FORCE ROW LEVEL SECURITY. A current identity comes only
        # from membership in the event's chat; sender_id from the outbox payload
        # is not a substitute for a membership check.
        member_id = await _set_message_rls_identity(db, event.chat_id)
        if member_id is None:
            return

        # 1. Fetch the message.
        message = await db.get(models.Message, event.message_id)
        if not message:
            logger.error("Message %s not found for notification", event.message_id)
            return
        if message.chat_id != event.chat_id:
            logger.error(
                "Message %s does not belong to its event chat", event.message_id
            )
            return

        # 1b. Fetch the sender EXPLICITLY. Message.sender is lazy="noload" (the
        # N+1 guard — CLAUDE.md "ALL relationships must have explicit lazy=noload"),
        # so db.get(Message) leaves message.sender == None. Passing message.sender
        # straight to notify_new_message crashed on `sender.id` (AttributeError:
        # 'NoneType' has no attribute 'id') the first time this handler ran
        # end-to-end — the bug sat dormant for waves because the outbox produced
        # ZERO events until the Wave 205 SW-A capture-on-commit fix restored the
        # domain-event subsystem. Loading the User by sender_id makes new_message
        # broadcasts actually fire (and notification_service's
        # `(sender.profile and ...)` push-title guard already tolerates a
        # noload profile == None).
        sender = await db.get(models.User, message.sender_id)
        if sender is None:
            logger.error(
                "Sender %s not found for message %s",
                message.sender_id,
                event.message_id,
            )
            return
        # Attach the loaded sender so serialize_message includes the sender record
        # in the new_message broadcast (name/avatar on the recipient's live bubble)
        # instead of "sender": null. Same db session, both objects already loaded —
        # an in-memory relationship set, no extra query / flush.
        message.sender = sender

        # 2. Fetch chat with participants.
        chat = await repo.get_by_id(event.chat_id)
        if not chat:
            logger.error("Chat %s not found for notification", event.chat_id)
            return

        # 2b. Wave 207 — if this message is a reply, load the replied-to message
        # (get_message_by_id selectinloads its sender) so serialize_message can
        # embed the quote preview in the live new_message frame — the recipient
        # sees the quote immediately, not just on the next refetch. None when not
        # a reply, or when the target was hard-deleted (the SET NULL self-FK has
        # already nulled message.reply_to_message_id by the time we read it here).
        replied = (
            await repo.get_message_by_id(
                message.reply_to_message_id,
                user_id=member_id,
                chat_id=event.chat_id,
            )
            if message.reply_to_message_id is not None
            else None
        )

        # 3. Trigger notifications
        # Wave 210 G3 — pass the chat's identity so a GROUP push is titled by the
        # group name + sender-prefixed body (DMs keep the sender-name title). chat
        # is a ChatDTO from get_by_id, so chat_type/name are already loaded.
        service = ChatNotificationService(db)
        await service.notify_new_message(
            message=message,
            chat_participants=chat.participants,
            sender=sender,
            replied=replied,
            chat_type=chat.chat_type,
            chat_name=chat.name,
        )
        # Handle transaction for delivery.py updates
        await db.commit()


async def handle_message_edited(event: MessageEdited) -> None:
    """Broadcast the committed current state for an edited-message event."""
    if event.message_id is None or event.chat_id is None:
        raise ValueError("message edit event is missing its identifiers")

    async with async_session() as db:
        if await _set_message_rls_identity(db, event.chat_id) is None:
            return
        message = await db.get(models.Message, event.message_id)
        if message is None:
            return
        if message.chat_id != event.chat_id:
            raise ValueError("message edit event chat does not match the row")
        # A later delete may commit before this event is delivered. Do not send
        # the old text after a tombstone; the ordered delete event will publish it.
        if message.deleted_at is not None:
            return
        if message.edited_at is None:
            raise ValueError("message edit event points to an unedited row")
        frame = {
            "type": "message_edited",
            "message_id": str(message.id),
            "chat_id": str(message.chat_id),
            "content": message.content,
            "edited_at": message.edited_at.isoformat(),
        }

    from app.api.ws.connection_manager import manager as ws_manager

    await ws_manager.broadcast_to_chat(
        event.chat_id, frame, propagate_nats_failure=True
    )


async def handle_message_deleted(event: MessageDeleted) -> None:
    """Broadcast the committed tombstone for a soft-deleted message."""
    if event.message_id is None or event.chat_id is None:
        raise ValueError("message delete event is missing its identifiers")

    async with async_session() as db:
        if await _set_message_rls_identity(db, event.chat_id) is None:
            return
        message = await db.get(models.Message, event.message_id)
        if message is None:
            return
        if message.chat_id != event.chat_id:
            raise ValueError("message delete event chat does not match the row")
        if message.deleted_at is None:
            raise ValueError("message delete event points to a live row")
        frame = {
            "type": "message_deleted",
            "message_id": str(message.id),
            "chat_id": str(message.chat_id),
            "deleted_at": message.deleted_at.isoformat(),
        }

    from app.api.ws.connection_manager import manager as ws_manager

    await ws_manager.broadcast_to_chat(
        event.chat_id, frame, propagate_nats_failure=True
    )


async def handle_chat_deleted(event: ChatDeleted) -> None:
    """Invalidate ws-hub auth cache for a deleted chat participant.

    RED-04 (audit 2026-03-14): Called by OutboxWorker from the stored ChatDeleted
    event, providing at-least-once delivery semantics.  If the immediate best-effort
    call in delete_chat() already succeeded, this is a no-op (ws-hub invalidation
    is idempotent).  If it failed, OutboxWorker retries until success.
    """
    from app.services.ws_hub_client import invalidate_ws_hub_cache

    await invalidate_ws_hub_cache(str(event.participant_id), str(event.chat_id))
    logger.debug(
        "ws-hub cache invalidated via outbox: chat=%s participant=%s",
        event.chat_id,
        event.participant_id,
    )


async def handle_chat_participant_removed(event: ChatParticipantRemoved) -> None:
    """Durably evict a removed participant from the ws-hub chat room."""
    if event.chat_id is None or event.user_id is None:
        raise ValueError("chat participant removal event is missing its identifiers")

    from app.services.ws_hub_client import invalidate_ws_hub_cache

    await invalidate_ws_hub_cache(
        str(event.user_id),
        str(event.chat_id),
        evict_room=True,
        event_id=event.event_id,
        raise_on_failure=True,
    )
    logger.debug(
        "ws-hub room membership revoked via outbox: chat=%s participant=%s",
        event.chat_id,
        event.user_id,
    )


async def handle_notifications_requested(event: NotificationsRequested) -> None:
    """Redeliver requested notifications through the transactional outbox."""
    if not event.notification_ids:
        return

    from app.services.notifications.delivery import (
        NotificationRedeliveryError,
        redeliver_notifications,
    )

    logger.info(
        "NotificationsRequested: %d notification(s) to deliver (channel=%s)",
        len(event.notification_ids),
        event.channel,
    )
    async with async_session() as db:
        outcome = await redeliver_notifications(
            db,
            notification_ids=event.notification_ids,
            channel=event.channel,
            payload_data=event.payload_data,
        )
        # Persist successful recipients and failed-attempt evidence before the
        # retry signal escapes to OutboxWorker. A replay then sends only pairs
        # without a committed successful delivery row.
        await db.commit()
    if outcome.retryable_failures:
        raise NotificationRedeliveryError(outcome)


async def handle_attachment_cleanup_requested(
    event: AttachmentCleanupRequested,
) -> None:
    """Delete files from static/S3 storage after chat history clear or chat delete.

    PERF-W10-05: Called by OutboxWorker with at-least-once delivery semantics.
    If the delete fails, the OutboxWorker retries until max_retries is reached,
    at which point the event moves to the Dead Letter Queue for explicit
    operator remediation. There is no automatic orphan-file GC for these
    objects; do not acknowledge an unverifiable deletion.
    """
    if not event.attachment_urls:
        return

    from app.services.chat.attachment_service import ChatAttachmentService

    service = ChatAttachmentService()
    urls = list(dict.fromkeys(url for url in event.attachment_urls if url))
    deleted = 0
    skipped = 0
    # Old forwarding copied Attachment rows but reused their object URL.
    # Query *after* the delete transaction commits: any remaining row owns
    # the blob, including one in another chat. A later deletion of that last
    # row schedules its own cleanup event. Bound query parameters and storage
    # work for historical bulk events, including at-least-once replays.
    for offset in range(0, len(urls), 128):
        candidate_urls = urls[offset : offset + 128]
        async with async_session() as db:
            result = await db.execute(
                select(models.Attachment.url)
                .where(models.Attachment.url.in_(candidate_urls))
                .distinct()
            )
            referenced = set(result.scalars().all())
        unreferenced = [url for url in candidate_urls if url not in referenced]
        skipped += len(candidate_urls) - len(unreferenced)
        if unreferenced:
            await service.cleanup_files(unreferenced, durable=True)
            deleted += len(unreferenced)
    logger.info(
        "attachment_cleanup_requested: deleted %d file(s), retained %d referenced file(s) for chat=%s",
        deleted,
        skipped,
        event.chat_id,
    )


async def handle_schedule_changed(event: ScheduleUpdated | ScheduleDeleted) -> None:
    """Notify affected groups about a changed or cancelled lesson (outbox-delivered)."""
    from app.services.notifications.schedule_changes import (
        notify_about_schedule_change,
    )

    if isinstance(event, ScheduleDeleted):
        previous, current = event.previous_state, None
    else:
        previous, current = event.previous_state, event.current_state
    if not event.schedule_id or not previous:
        # Legacy rows predate the before/after snapshot; there is nothing to diff.
        logger.info("Skipping schedule notification without a change snapshot")
        return
    async with async_session() as db:
        await notify_about_schedule_change(
            db, schedule_id=event.schedule_id, previous=previous, current=current
        )
        await db.commit()


async def acknowledge_audit_only_event(event: DomainEvent) -> None:
    """Acknowledge persisted audit events that have no delivery side effect.

    These event types are intentionally subscribed explicitly: an unregistered
    durable event must still fail closed instead of being silently marked done.
    """


def configure_event_handlers() -> None:
    """
    Register all event handlers with the global event bus.

    This should be called during application startup (lifespan).
    """
    # Subscribe to all events for logging
    event_bus.subscribe_all(log_all_events)

    # Register specific handlers
    event_bus.subscribe("user.created", handle_user_created)  # type: ignore[arg-type]
    event_bus.subscribe("auth.login", handle_user_logged_in)  # type: ignore[arg-type]
    event_bus.subscribe("auth.mfa_enabled", handle_mfa_enabled)  # type: ignore[arg-type]
    event_bus.subscribe(
        "auth.mfa_email.requested",
        handle_mfa_email_delivery_requested,  # type: ignore[arg-type]
    )
    event_bus.subscribe("event.created", handle_event_created)  # type: ignore[arg-type]
    event_bus.subscribe("event.created", generate_event_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("event.updated", generate_event_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("news.created", generate_news_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("news.updated", generate_news_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("event.created", index_event_for_search)  # type: ignore[arg-type]
    event_bus.subscribe("event.updated", index_event_for_search)  # type: ignore[arg-type]
    event_bus.subscribe("news.created", index_news_for_search)  # type: ignore[arg-type]
    event_bus.subscribe("news.updated", index_news_for_search)  # type: ignore[arg-type]
    event_bus.subscribe("event.registration", handle_event_registration)  # type: ignore[arg-type]
    event_bus.subscribe("notification.sent", handle_notification_sent)  # type: ignore[arg-type]
    event_bus.subscribe("chat.message_sent", handle_message_sent)  # type: ignore[arg-type]
    event_bus.subscribe("chat.message_edited", handle_message_edited)  # type: ignore[arg-type]
    event_bus.subscribe("chat.message_deleted", handle_message_deleted)  # type: ignore[arg-type]
    # Outbox-delivered lesson changes notify the affected groups (schedule.changed).
    event_bus.subscribe("SCHEDULE_UPDATED", handle_schedule_changed)  # type: ignore[arg-type]
    event_bus.subscribe("SCHEDULE_DELETED", handle_schedule_changed)  # type: ignore[arg-type]
    for event_type in (
        "SCHEDULE_CREATED",
        "GRADE_ASSIGNED",
        "GRADE_MODIFIED",
        "NOTIFICATION_DEAD_LETTER_RETRY",
        "NOTIFICATION_DEAD_LETTER_PURGE",
    ):
        event_bus.subscribe(event_type, acknowledge_audit_only_event)
    # RED-04: OutboxWorker delivers ChatDeleted events with at-least-once guarantees.
    event_bus.subscribe("chat.deleted", handle_chat_deleted)  # type: ignore[arg-type]
    event_bus.subscribe(
        "chat.participant_removed",
        handle_chat_participant_removed,  # type: ignore[arg-type]
    )
    # PERF-W10-05: OutboxWorker delivers file cleanup with at-least-once guarantees.
    event_bus.subscribe(
        "chat.attachment_cleanup_requested",
        handle_attachment_cleanup_requested,  # type: ignore[arg-type]
    )
    # RED-02: OutboxWorker delivers NotificationsRequested events for at-least-once push.
    event_bus.subscribe(
        "notification.delivery_requested",
        handle_notifications_requested,  # type: ignore[arg-type]
    )

    logger.info("Domain event handlers configured")


__all__ = [
    "configure_event_handlers",
    "handle_event_created",
    "handle_event_registration",
    "handle_message_deleted",
    "handle_message_edited",
    "handle_message_sent",
    "handle_mfa_email_delivery_requested",
    "handle_mfa_enabled",
    "handle_notification_sent",
    "handle_notifications_requested",
    "handle_user_created",
    "handle_user_logged_in",
    "log_all_events",
]
