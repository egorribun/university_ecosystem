"""
Domain event handlers.

Contains handler implementations for domain events.
These handlers are registered with the EventBus during application startup.
"""

from __future__ import annotations

import logging

from app.core.container import get_vector_service
from app.core.database import async_session
from app.core.events import (
    DomainEvent,
    EventCreated,
    EventRegistration,
    MessageSent,
    MfaEnabled,
    NewsCreated,
    NotificationSent,
    UserCreated,
    UserLoggedIn,
    event_bus,
)
from app.models import models

logger = logging.getLogger(__name__)


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
        "New user registered: user_id=%d, email=%s",
        event.user_id,
        event.email,
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

        # 1. Fetch message with sender (joined)
        message = await db.get(models.Message, event.message_id)
        if not message:
            logger.error("Message %s not found for notification", event.message_id)
            return

        # 2. Fetch chat with participants
        chat = await repo.get_by_id(event.chat_id)
        if not chat:
            logger.error("Chat %s not found for notification", event.chat_id)
            return

        # 3. Trigger notifications
        service = ChatNotificationService(db)
        await service.notify_new_message(
            message=message,
            chat_participants=chat.participants,
            sender=message.sender,
        )
        # Handle transaction for delivery.py updates
        await db.commit()


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

    logger.info("Domain event handlers configured")


__all__ = [
    "configure_event_handlers",
    "handle_event_created",
    "handle_event_registration",
    "handle_mfa_enabled",
    "handle_notification_sent",
    "handle_user_created",
    "handle_user_logged_in",
    "log_all_events",
]
