"""
Domain events system for loose coupling.

Provides an event bus for publishing and subscribing to domain events.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from abc import ABC
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

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
    user_id: UUID | None = None
    source: str = "app"
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class DomainEvent(ABC):  # noqa: B024
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: EventMetadata = field(default_factory=EventMetadata)

    # ClassVar string identifying the event. Subclasses MUST override this.
    EVENT_TYPE: ClassVar[str] = "domain_event.base"

    @property
    def event_type(self) -> str:
        """Return the event type name (backward compatibility)."""
        return self.EVENT_TYPE


# ── Event Registry ────────────────────────────────────────────────────────────

_EVENT_REGISTRY: dict[str, type[DomainEvent]] = {}


def register_domain_event(cls: type[DomainEvent]) -> type[DomainEvent]:
    """Register a DomainEvent subclass for safe Outbox/CDC deserialization.

    HIGH-04 (audit 2026-03-11): Replaces the insecure blind ``setattr`` pattern
    used during event reconstruction. By registering allowed event types, we
    ensure only intended classes are instantiated and only known fields are
    populated using standard dataclass constructors.

    Registers the class under both its class name and its ``event_type`` property.
    """
    _EVENT_REGISTRY[cls.__name__] = cls
    if hasattr(cls, "EVENT_TYPE"):
        _EVENT_REGISTRY[cls.EVENT_TYPE] = cls
    return cls


# User Events
@register_domain_event
@dataclass
class UserCreated(DomainEvent):
    """Fired when a new user is created."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None
    email: str = ""

    EVENT_TYPE: ClassVar[str] = "user.created"

    @classmethod
    def from_dict(cls, data: dict) -> "UserCreated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class UserUpdated(DomainEvent):
    """Fired when a user profile is updated."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None
    updated_fields: list[str] = field(default_factory=list)

    EVENT_TYPE: ClassVar[str] = "user.updated"

    @classmethod
    def from_dict(cls, data: dict) -> "UserUpdated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class UserDeleted(DomainEvent):
    """Fired when a user is deleted."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None

    EVENT_TYPE: ClassVar[str] = "user.deleted"

    @classmethod
    def from_dict(cls, data: dict) -> "UserDeleted":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


# Auth Events
@register_domain_event
@dataclass
class UserLoggedIn(DomainEvent):
    """Fired when a user logs in successfully."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None
    ip_address: str | None = None

    EVENT_TYPE: ClassVar[str] = "auth.login"

    @classmethod
    def from_dict(cls, data: dict) -> "UserLoggedIn":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class MfaEnabled(DomainEvent):
    """Fired when MFA is enabled for a user."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None
    method: str = "totp"

    EVENT_TYPE: ClassVar[str] = "auth.mfa_enabled"

    @classmethod
    def from_dict(cls, data: dict) -> "MfaEnabled":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


# Event Events
@register_domain_event
@dataclass
class EventCreated(DomainEvent):
    """Fired when a new event is created."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    event_id_entity: UUID | None = None
    organizer_id: UUID | None = None
    title: str = ""

    EVENT_TYPE: ClassVar[str] = "event.created"

    @classmethod
    def from_dict(cls, data: dict) -> "EventCreated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class EventUpdated(DomainEvent):
    """Fired when an existing event is updated."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    event_id_entity: UUID | None = None
    title: str = ""

    EVENT_TYPE: ClassVar[str] = "event.updated"

    @classmethod
    def from_dict(cls, data: dict) -> "EventUpdated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class EventRegistration(DomainEvent):
    """Fired when a user registers for an event."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    event_id_entity: UUID | None = None
    user_id: UUID | None = None

    EVENT_TYPE: ClassVar[str] = "event.registration"

    @classmethod
    def from_dict(cls, data: dict) -> "EventRegistration":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class NewsCreated(DomainEvent):
    """Fired when a new news article is created."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    news_id: UUID | None = None
    title: str = ""

    EVENT_TYPE: ClassVar[str] = "news.created"

    @classmethod
    def from_dict(cls, data: dict) -> "NewsCreated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class NewsUpdated(DomainEvent):
    """Fired when an existing news article is updated."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    news_id: UUID | None = None
    title: str = ""

    EVENT_TYPE: ClassVar[str] = "news.updated"

    @classmethod
    def from_dict(cls, data: dict) -> "NewsUpdated":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


# Notification Events
@register_domain_event
@dataclass
class MessageSent(DomainEvent):
    """Fired when a new message is sent."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    message_id: UUID | None = None
    chat_id: UUID | None = None
    sender_id: UUID | None = None
    content_preview: str = ""

    EVENT_TYPE: ClassVar[str] = "chat.message_sent"

    @classmethod
    def from_dict(cls, data: dict) -> "MessageSent":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class ChatDeleted(DomainEvent):
    """Fired when a chat is permanently deleted.

    RED-04 (audit 2026-03-14): Recorded atomically with the DELETE in the same
    DB transaction.  OutboxWorker picks it up and calls ws-hub cache invalidation
    with at-least-once delivery guarantees — closing the 60 s BOLA window that
    existed when invalidation was best-effort post-commit.
    """

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    chat_id: UUID | None = None
    participant_id: UUID | None = None

    EVENT_TYPE: ClassVar[str] = "chat.deleted"

    @classmethod
    def from_dict(cls, data: dict) -> "ChatDeleted":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class NotificationSent(DomainEvent):
    """Fired when a notification is sent."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    notification_id: str = ""
    user_id: UUID | None = None
    notification_type: str = ""

    EVENT_TYPE: ClassVar[str] = "notification.sent"

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationSent":
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {f.name for f in dataclasses.fields(cls) if f.name not in ("event_id", "occurred_at", "metadata")}
        return cls(**{k: v for k, v in data.items() if k in known})


class EventEmitterMixin:
    """Mixin for models that emit domain events to be persisted."""

    _pending_domain_events: list[DomainEvent]

    def record_event(self, event: DomainEvent) -> None:
        """Queue a domain event for persistence (Thread-safe init)."""
        # SEC-004: Atomic-like initialization of the list to prevent race conditions
        # in the common hasattr -> setattr pattern during concurrent flushes.
        if "_pending_domain_events" not in self.__dict__:
            # Use object.__setattr__ for bypass to avoid any potential proxy interference
            object.__setattr__(self, "_pending_domain_events", [])
        self._pending_domain_events.append(event)

    def clear_events(self) -> None:
        """Clear all pending events."""
        object.__setattr__(self, "_pending_domain_events", [])


def capture_domain_events(
    session: Session, flush_context: Any, instances: Any = None
) -> None:
    """SQLAlchemy listener to capture and persist domain events to the database."""
    from app.models.domain_events import StoredEvent

    events_to_store = []

    # Pre-filter using generator/comprehension for C-level speed, checking only for the attribute
    changed_objects = session.new | session.dirty | session.deleted
    emitters = (
        obj for obj in changed_objects if getattr(obj, "_pending_domain_events", None)
    )

    for obj in emitters:
        for event_data in obj._pending_domain_events:
            # We'll use a simpler approach: serialize the entire event if possible,
            # or just use its __dict__ without the base DomainEvent fields.

            payload = {
                "_schema_version": getattr(event_data, "EVENT_VERSION", 1),  # DEBT-02: schema version
                **{
                    k: v
                    for k, v in event_data.__dict__.items()
                    if k not in ("event_id", "occurred_at", "metadata")
                },
            }

            # SEC-007 (Wave 6 audit): Safe ID extraction with typed validation.
            # Prevents storing junk stringified complex objects as IDs.
            raw_id = getattr(obj, "id", "unknown")
            if not isinstance(raw_id, (str, UUID, int)):
                # If ID is complex or None, we log and fall back to "unknown" rather than str([])
                logger.warning(
                    "Unsafe aggregate ID detected",
                    extra={"aggregate_type": obj.__class__.__name__},
                )
                raw_id = "unknown"

            stored_event = StoredEvent(
                event_type=event_data.event_type,
                aggregate_type=obj.__class__.__name__,
                aggregate_id=str(raw_id),
                # DEBT-01: Populate aggregate_id_uuid when the ID is a UUID so the
                # outbox worker can use DISTINCT ON (aggregate_id_uuid) for
                # per-aggregate causal ordering across multiple workers.
                aggregate_id_uuid=raw_id if isinstance(raw_id, UUID) else None,
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
        session.add_all(events_to_store)


async def register_event_listeners() -> None:
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

        # Execute the chain with a global failsafe timeout (PERF-002).
        # Ensures a slow or stuck middleware/handler doesn't hang the request thread.
        try:
            await asyncio.wait_for(handler_chain(event), timeout=10.0)
        except TimeoutError:
            logger.error(
                "Event production timed out (10s)",
                extra={
                    "event_type": event_type,
                    "event_id": event.event_id,
                },
            )

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
                try:
                    await self._dlq.add(event, e, handler.__name__)
                except Exception as dlq_err:
                    # NEW-SEC-003: Critical fallback. If DLQ fails, we MUST ensure
                    # the error is catastrophic and visible.
                    logger.critical(
                        "DOMAIN EVENT LOST: Both handler and DLQ failed",
                        extra={
                            "original_error": str(e),
                            "dlq_error": str(dlq_err),
                            "event_type": event.event_type,
                            "event_id": event.event_id,
                        },
                    )


# Global event bus instance
event_bus = EventBus()


__all__ = [
    "ChatDeleted",
    "DomainEvent",
    "EventBus",
    "EventCreated",
    "EventEmitterMixin",
    "EventHandler",
    "EventMetadata",
    "EventMiddleware",
    "EventRegistration",
    "EventUpdated",
    "MessageSent",
    "MfaEnabled",
    "NewsCreated",
    "NewsUpdated",
    "NotificationSent",
    "UserCreated",
    "UserDeleted",
    "UserLoggedIn",
    "UserUpdated",
    "event_bus",
    "register_event_listeners",
]
