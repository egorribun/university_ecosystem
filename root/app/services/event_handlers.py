"""
Domain event handlers.

Contains handler implementations for domain events.
These handlers are registered with the EventBus during application startup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.events import (
    DomainEvent,
    EventCreated,
    EventRegistration,
    MfaEnabled,
    NotificationSent,
    UserCreated,
    UserLoggedIn,
    event_bus,
)

if TYPE_CHECKING:
    from app.core.cache import MultiLayerCache

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


def configure_event_handlers() -> None:
    """
    Register all event handlers with the global event bus.

    This should be called during application startup (lifespan).
    """
    # Subscribe to all events for logging
    event_bus.subscribe_all(log_all_events)

    # Register specific handlers
    event_bus.subscribe("user.created", handle_user_created)
    event_bus.subscribe("auth.login", handle_user_logged_in)
    event_bus.subscribe("auth.mfa_enabled", handle_mfa_enabled)
    event_bus.subscribe("event.created", handle_event_created)
    event_bus.subscribe("event.registration", handle_event_registration)
    event_bus.subscribe("notification.sent", handle_notification_sent)

    logger.info("Domain event handlers configured")


__all__ = [
    "configure_event_handlers",
    "log_all_events",
    "handle_user_created",
    "handle_user_logged_in",
    "handle_mfa_enabled",
    "handle_event_created",
    "handle_event_registration",
    "handle_notification_sent",
]
