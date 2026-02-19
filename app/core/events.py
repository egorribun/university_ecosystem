"""
Domain events system for loose coupling.

Provides an event bus for publishing and subscribing to domain events.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.event_dlq import DeadLetterQueue

logger = logging.getLogger(__name__)

EventHandler = Callable[["DomainEvent"], Coroutine[Any, Any, None]]
EventMiddleware = Callable[
    ["DomainEvent", Callable[["DomainEvent"], Coroutine[Any, Any, None]]],
    Coroutine[Any, Any, None],
]


@dataclass
class EventMetadata:
    """Metadata attached to every event for tracing and retry tracking."""

    correlation_id: str | None = None
    causation_id: str | None = None
    user_id: int | None = None
    source: str = "app"
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class DomainEvent(ABC):
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: EventMetadata = field(default_factory=EventMetadata)

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
class EventUpdated(DomainEvent):
    """Fired when an existing event is updated."""

    event_id_entity: int = 0
    title: str = ""

    @property
    def event_type(self) -> str:
        return "event.updated"


@dataclass
class EventRegistration(DomainEvent):
    """Fired when a user registers for an event."""

    event_id_entity: int = 0
    user_id: int = 0

    @property
    def event_type(self) -> str:
        return "event.registration"


@dataclass
class NewsCreated(DomainEvent):
    """Fired when a new news article is created."""

    news_id: int = 0
    title: str = ""

    @property
    def event_type(self) -> str:
        return "news.created"


@dataclass
class NewsUpdated(DomainEvent):
    """Fired when an existing news article is updated."""

    news_id: int = 0
    title: str = ""

    @property
    def event_type(self) -> str:
        return "news.updated"


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


class EventEmitterMixin:
    """Mixin for models that emit domain events to be persisted."""

    def record_event(self, event: DomainEvent) -> None:
        """Queue a domain event for persistence."""
        if not hasattr(self, "_pending_domain_events"):
            self._pending_domain_events: list[DomainEvent] = []
        self._pending_domain_events.append(event)

    def clear_events(self) -> None:
        """Clear all pending events."""
        self._pending_domain_events = []


def capture_domain_events(
    session: Session, flush_context: Any, instances: Any = None
) -> None:
    """SQLAlchemy listener to capture and persist domain events to the database."""
    from app.models.domain_events import StoredEvent

    events_to_store = []

    # Check all objects in session for pending events
    # We use session.new | session.dirty | session.deleted to catch all changes
    for obj in session.new | session.dirty | session.deleted:
        if isinstance(obj, EventEmitterMixin) and hasattr(
            obj, "_pending_domain_events"
        ):
            for event_data in obj._pending_domain_events:
                # payload = asdict(event_data)
                # But event_data might have metadata we don't want in payload
                # We'll use a simpler approach: serialize the entire event if possible,
                # or just use its __dict__ without the base DomainEvent fields.

                payload = {
                    k: v
                    for k, v in event_data.__dict__.items()
                    if k not in ("event_id", "occurred_at", "metadata")
                }

                stored_event = StoredEvent(
                    event_type=event_data.event_type,
                    aggregate_type=obj.__class__.__name__,
                    aggregate_id=str(getattr(obj, "id", "unknown")),
                    payload=payload,
                    metadata_={
                        "event_id": event_data.event_id,
                        "occurred_at": event_data.occurred_at.isoformat(),
                        "correlation_id": event_data.metadata.correlation_id,
                        "user_id": event_data.metadata.user_id,
                    },
                )
                events_to_store.append(stored_event)

            # Clear pending events after capturing
            obj.clear_events()

    if events_to_store:
        for event_to_add in events_to_store:
            session.add(event_to_add)


def register_event_listeners():
    """Register domain event capturing listeners for all sessions."""
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    sa_event.listen(Session, "after_flush", capture_domain_events)
    logger.info("Domain event persistence listeners registered.")


class EventBus:
    """
    In-memory event bus for domain events.

    Supports:
    - Async handlers with concurrent execution
    - Wildcard subscriptions (subscribe to all events)
    - Middleware pipeline for cross-cutting concerns
    - Dead Letter Queue integration for failed events
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._all_handlers: list[EventHandler] = []
        self._middleware: list[EventMiddleware] = []
        self._dlq: DeadLetterQueue | None = None

    def add_middleware(self, middleware: EventMiddleware) -> None:
        """
        Add middleware to the processing pipeline.

        Middleware is executed in order added (first added = outermost).
        """
        self._middleware.append(middleware)
        logger.debug(
            "Middleware added: %s",
            getattr(middleware, "__name__", type(middleware).__name__),
        )

    def set_dlq(self, dlq: DeadLetterQueue) -> None:
        """Set the Dead Letter Queue for failed events."""
        self._dlq = dlq

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

    def unsubscribe_all(self, handler: EventHandler) -> None:
        """Unsubscribe a handler from all events."""
        if handler in self._all_handlers:
            self._all_handlers.remove(handler)

    def clear(self) -> None:
        """Clear all handlers and middleware."""
        self._handlers.clear()
        self._all_handlers.clear()
        self._middleware.clear()

    def get_handler_count(self, event_type: str | None = None) -> int:
        """Get number of handlers for a specific event type or all."""
        if event_type:
            return len(self._handlers.get(event_type, [])) + len(self._all_handlers)
        return sum(len(h) for h in self._handlers.values()) + len(self._all_handlers)

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish an event through the middleware pipeline to all handlers.

        Handlers are executed concurrently.
        """
        event_type = event.event_type
        handlers = self._handlers.get(event_type, []) + self._all_handlers

        if not handlers:
            logger.debug("No handlers for event %s", event_type)
            return

        logger.debug("Publishing %s to %d handlers", event_type, len(handlers))

        # Define the core handler execution
        async def execute_handlers(evt: DomainEvent) -> None:
            tasks = [
                asyncio.create_task(self._safe_handle(handler, evt))
                for handler in handlers
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Build middleware chain (last added wraps innermost)
        handler_chain = execute_handlers
        for middleware in reversed(self._middleware):
            prev_handler = handler_chain

            async def wrapped(
                evt: DomainEvent,
                _mw: EventMiddleware = middleware,
                _next: Any = prev_handler,
            ) -> None:
                await _mw(evt, _next)

            handler_chain = wrapped

        # Execute the chain
        await handler_chain(event)

    async def _safe_handle(self, handler: EventHandler, event: DomainEvent) -> None:
        """Execute handler with error protection and optional DLQ."""
        try:
            await handler(event)
        except Exception as e:
            logger.exception(
                "Handler %s failed for event %s: %s",
                handler.__name__,
                event.event_type,
                e,
            )
            # Send to DLQ if configured
            if self._dlq is not None:
                await self._dlq.add(event, e, handler.__name__)


# Global event bus instance
event_bus = EventBus()


__all__ = [
    # Core
    "DomainEvent",
    "EventBus",
    # Event events
    "EventCreated",
    # Persistence
    "EventEmitterMixin",
    # Types
    "EventHandler",
    "EventMetadata",
    "EventMiddleware",
    "EventRegistration",
    "EventUpdated",
    "MfaEnabled",
    # News events
    "NewsCreated",
    "NewsUpdated",
    # Notification events
    "NotificationSent",
    # User events
    "UserCreated",
    "UserDeleted",
    # Auth events
    "UserLoggedIn",
    "UserUpdated",
    "event_bus",
    "register_event_listeners",
]
