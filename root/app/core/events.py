"""
Domain events system for loose coupling.

Provides an event bus for publishing and subscribing to domain events.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine
from uuid import uuid4

logger = logging.getLogger(__name__)

EventHandler = Callable[["DomainEvent"], Coroutine[Any, Any, None]]


@dataclass
class DomainEvent(ABC):
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Return the event type name."""
        ...


# User Events
@dataclass
class UserCreated(DomainEvent):
    """Fired when a new user is created."""

    user_id: int = 0
    email: str = ""

    @property
    def event_type(self) -> str:
        return "user.created"


@dataclass
class UserUpdated(DomainEvent):
    """Fired when a user profile is updated."""

    user_id: int = 0
    updated_fields: list[str] = field(default_factory=list)

    @property
    def event_type(self) -> str:
        return "user.updated"


@dataclass
class UserDeleted(DomainEvent):
    """Fired when a user is deleted."""

    user_id: int = 0

    @property
    def event_type(self) -> str:
        return "user.deleted"


# Auth Events
@dataclass
class UserLoggedIn(DomainEvent):
    """Fired when a user logs in successfully."""

    user_id: int = 0
    ip_address: str | None = None

    @property
    def event_type(self) -> str:
        return "auth.login"


@dataclass
class MfaEnabled(DomainEvent):
    """Fired when MFA is enabled for a user."""

    user_id: int = 0
    method: str = "totp"

    @property
    def event_type(self) -> str:
        return "auth.mfa_enabled"


# Event Events
@dataclass
class EventCreated(DomainEvent):
    """Fired when a new event is created."""

    event_id_entity: int = 0
    organizer_id: int = 0
    title: str = ""

    @property
    def event_type(self) -> str:
        return "event.created"


@dataclass
class EventRegistration(DomainEvent):
    """Fired when a user registers for an event."""

    event_id_entity: int = 0
    user_id: int = 0

    @property
    def event_type(self) -> str:
        return "event.registration"


# Notification Events
@dataclass
class NotificationSent(DomainEvent):
    """Fired when a notification is sent."""

    notification_id: str = ""
    user_id: int = 0
    notification_type: str = ""

    @property
    def event_type(self) -> str:
        return "notification.sent"


class EventBus:
    """
    Simple in-memory event bus for domain events.

    Supports async handlers and wildcard subscriptions.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._all_handlers: list[EventHandler] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to a specific event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Handler subscribed to %s", event_type)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe a handler to all events."""
        self._all_handlers.append(handler)
        logger.debug("Handler subscribed to all events")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish an event to all interested handlers.

        Handlers are executed concurrently.
        """
        event_type = event.event_type
        handlers = self._handlers.get(event_type, []) + self._all_handlers

        if not handlers:
            logger.debug("No handlers for event %s", event_type)
            return

        logger.debug(
            "Publishing %s to %d handlers", event_type, len(handlers)
        )

        # Execute handlers concurrently
        tasks = [
            asyncio.create_task(self._safe_handle(handler, event))
            for handler in handlers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_handle(
        self, handler: EventHandler, event: DomainEvent
    ) -> None:
        """Execute handler with error protection."""
        try:
            await handler(event)
        except Exception as e:
            logger.exception(
                "Handler %s failed for event %s: %s",
                handler.__name__,
                event.event_type,
                e,
            )


# Global event bus instance
event_bus = EventBus()


__all__ = [
    "DomainEvent",
    "EventBus",
    "event_bus",
    # User events
    "UserCreated",
    "UserUpdated",
    "UserDeleted",
    # Auth events
    "UserLoggedIn",
    "MfaEnabled",
    # Event events
    "EventCreated",
    "EventRegistration",
    # Notification events
    "NotificationSent",
]
