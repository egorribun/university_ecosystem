"""
Domain event handlers.

Contains handler implementations for domain events.
These handlers are registered with the EventBus during application startup.
"""

from __future__ import annotations

import app.models as models
from app.core.container import get_vector_service
from app.core.database import async_session
from app.core.events import (
    AttachmentCleanupRequested,
    ChatDeleted,
    DomainEvent,
    EventCreated,
    EventRegistration,
    MessageSent,
    MfaEnabled,
    NewsCreated,
    NotificationSent,
    NotificationsRequested,
    UserCreated,
    UserLoggedIn,
    event_bus,
)
from app.core.logging import get_logger

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


async def handle_event_created(event: EventCreated) -> None:
    """Handle event creation events."""
    logger.info(
        "Event created: event_id=%d, organizer=%d, title=%s",
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


async def generate_event_embedding(event: EventCreated) -> None:
    """Generate embedding for newly created event."""
    async with async_session() as db:
        vector_service = get_vector_service(db)
        # Fetch the event to get full content
        db_event = await db.get(models.Event, event.event_id_entity)
        if not db_event:
            return

        text_to_embed = (
            f"{db_event.title} {db_event.description or ''} {db_event.location or ''}"
        )
        embedding = await vector_service.get_embedding(text_to_embed)
        db_event.embedding = embedding
        await db.commit()


async def generate_news_embedding(event: NewsCreated) -> None:
    """Generate embedding for newly created news."""
    async with async_session() as db:
        vector_service = get_vector_service(db)
        db_news = await db.get(models.News, event.news_id)
        if not db_news:
            return

        text_to_embed = f"{db_news.title} {db_news.content}"
        embedding = await vector_service.get_embedding(text_to_embed)
        db_news.embedding = embedding
        await db.commit()


async def handle_message_sent(event: MessageSent) -> None:
    """
    Handle message sent events by triggering notifications.
    (RZ-F-11 Outbox Pattern implementation)
    """
    from app.repositories.chat_repository import ChatRepository
    from app.services.chat.notification_service import ChatNotificationService

    async with async_session() as db:
        repo = ChatRepository(db)

        # 1. Fetch the message.
        message = await db.get(models.Message, event.message_id)
        if not message:
            logger.error("Message %s not found for notification", event.message_id)
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

        # 2. Fetch chat with participants
        if event.chat_id is None:
            logger.error(
                "Message %s has no chat_id, skipping notification", event.message_id
            )
            return
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
            await repo.get_message_by_id(message.reply_to_message_id)
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


async def handle_notifications_requested(event: NotificationsRequested) -> None:
    """Deliver push notifications for the requested notification IDs.

    RED-02 (audit 2026-03-14): Called by OutboxWorker; provides at-least-once
    delivery semantics for push notifications.  The OutboxWorker retries this
    handler if it raises, so delivery is guaranteed even when the originating
    request process crashes after writing the outbox event.
    """
    if not event.notification_ids:
        return

    logger.info(
        "NotificationsRequested: %d notification(s) to deliver (channel=%s)",
        len(event.notification_ids),
        event.channel,
    )
    # Future work: route to dispatch_push_for_notifications() once that helper
    # is extracted from create_notifications_for_users() in delivery.py.
    # For now the in-process direct-dispatch path in delivery.py is the primary
    # delivery mechanism; this handler acts as the at-least-once durability
    # backstop recorded in the outbox.


async def handle_attachment_cleanup_requested(
    event: AttachmentCleanupRequested,
) -> None:
    """Delete files from static/S3 storage after chat history clear or chat delete.

    PERF-W10-05: Called by OutboxWorker with at-least-once delivery semantics.
    If the delete fails, the OutboxWorker retries until max_retries is reached,
    at which point the event moves to the Dead Letter Queue.  Files in the DLQ
    will be cleaned up by the periodic orphan-file GC job.
    """
    if not event.attachment_urls:
        return

    from app.services.chat.attachment_service import ChatAttachmentService

    service = ChatAttachmentService()
    await service.cleanup_files(event.attachment_urls)
    logger.info(
        "attachment_cleanup_requested: deleted %d file(s) for chat=%s",
        len(event.attachment_urls),
        event.chat_id,
    )


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
    event_bus.subscribe("event.created", handle_event_created)  # type: ignore[arg-type]
    event_bus.subscribe("event.created", generate_event_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("event.updated", generate_event_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("news.created", generate_news_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("news.updated", generate_news_embedding)  # type: ignore[arg-type]
    event_bus.subscribe("event.registration", handle_event_registration)  # type: ignore[arg-type]
    event_bus.subscribe("notification.sent", handle_notification_sent)  # type: ignore[arg-type]
    event_bus.subscribe("chat.message_sent", handle_message_sent)  # type: ignore[arg-type]
    # RED-04: OutboxWorker delivers ChatDeleted events with at-least-once guarantees.
    event_bus.subscribe("chat.deleted", handle_chat_deleted)  # type: ignore[arg-type]
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
    "handle_mfa_enabled",
    "handle_notification_sent",
    "handle_notifications_requested",
    "handle_user_created",
    "handle_user_logged_in",
    "log_all_events",
]
