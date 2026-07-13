"""
Domain events system for loose coupling.

Provides an event bus for publishing and subscribing to domain events.
"""

from __future__ import annotations

import asyncio
import dataclasses
from abc import ABC
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.event_dlq import DeadLetterQueue

logger = get_logger(__name__)

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


def get_registered_events() -> dict[str, type[DomainEvent]]:
    """Return a read-only snapshot of the event registry.

    Used by ``app.workers.outbox`` to reconstruct DomainEvent subclasses from
    stored ``event_type`` strings, and by tests/introspection tooling to list
    all registered domain events.
    """
    return dict(_EVENT_REGISTRY)


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
    def from_dict(cls, data: dict[str, Any]) -> UserCreated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> UserUpdated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class UserDeleted(DomainEvent):
    """Fired when a user is deleted."""

    EVENT_VERSION: ClassVar[int] = 1  # Increment on breaking schema changes

    user_id: UUID | None = None

    EVENT_TYPE: ClassVar[str] = "user.deleted"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserDeleted:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> UserLoggedIn:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> MfaEnabled:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> EventCreated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> EventUpdated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> EventRegistration:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> NewsCreated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> NewsUpdated:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> MessageSent:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> ChatDeleted:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class AttachmentCleanupRequested(DomainEvent):
    """Scheduled deletion of S3/static attachment files.

    PERF-W10-05: Replaces inline ``cleanup_files()`` calls in clear_history()
    and delete_chat().  By recording this event INSIDE the same DB transaction
    as the message/chat DELETE, we get atomicity: either the row is deleted AND
    the cleanup is scheduled, or neither happens.  OutboxWorker retries with
    at-least-once delivery semantics so files are eventually removed even if the
    process crashes between commit and the S3 delete call.

    Payload: ``attachment_urls`` is a list of relative or absolute URLs returned
    by ``ChatAttachmentService.collect_urls()``.
    """

    EVENT_VERSION: ClassVar[int] = 1

    chat_id: UUID | None = None
    attachment_urls: list[str] = field(default_factory=list)

    EVENT_TYPE: ClassVar[str] = "chat.attachment_cleanup_requested"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttachmentCleanupRequested:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
    def from_dict(cls, data: dict[str, Any]) -> NotificationSent:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        # Add migration logic here when EVENT_VERSION is incremented
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
        return cls(**{k: v for k, v in data.items() if k in known})


@register_domain_event
@dataclass
class NotificationsRequested(DomainEvent):
    """Fired when notifications need to be delivered to users.

    RED-02 (audit 2026-03-14): Replaces direct push dispatch in
    create_notifications_for_users(). The OutboxWorker picks this up and
    triggers push delivery with at-least-once semantics.
    """

    EVENT_VERSION: ClassVar[int] = 1

    notification_ids: list[str] = field(default_factory=list)
    channel: str = "push"

    EVENT_TYPE: ClassVar[str] = "notification.delivery_requested"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationsRequested:
        """Deserialize from stored payload, handling schema migrations."""
        data.pop("_schema_version", 1)
        known = {
            f.name
            for f in dataclasses.fields(cls)
            if f.name not in ("event_id", "occurred_at", "metadata")
        }
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
        # W205 SW-A: capture_domain_events scans only session.new|dirty|deleted, so
        # an aggregate that was already flushed before record_event is called (e.g.
        # a repository create_*() that flushes, THEN the command records the event)
        # is persistent — in none of those sets — and its StoredEvent (outbox row)
        # was silently dropped, breaking the ENTIRE domain-event subsystem. Register
        # the emitter on its session so capture can also scan tracked emitters. Only
        # objects that actually record an event are tracked (no identity-map scan).
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(self, raiseerr=False)
        session = state.session if state is not None else None
        if session is not None:
            session.info.setdefault("_event_emitters", set()).add(self)

    def clear_events(self) -> None:
        """Clear all pending events."""
        object.__setattr__(self, "_pending_domain_events", [])


def capture_domain_events(
    session: Session, flush_context: Any, instances: Any = None
) -> None:
    """SQLAlchemy listener to capture domain events; stores them after flush completes.

    HIGH-W19: This function only COLLECTS events and clears pending lists.
    The actual session.add_all() is deferred to the after_flush_postexec listener
    (_persist_captured_events) to avoid triggering a recursive flush.
    """
    from app.models.domain_events import StoredEvent

    events_to_store = []

    # Pre-filter using generator/comprehension for C-level speed, checking only for the attribute
    changed_objects = session.new | session.dirty | session.deleted
    # W205 SW-A: also scan emitters that recorded an event AFTER being flushed
    # (persistent → absent from new|dirty|deleted). record_event tracks them on
    # session.info["_event_emitters"]. Double-listing (an object in both new and
    # tracked) is harmless: clear_events() empties its list on the first pass, so
    # the second occurrence is filtered out by the truthiness check below.
    tracked = session.info.get("_event_emitters")
    candidate_objects = list(changed_objects)
    if tracked:
        candidate_objects.extend(tracked)
    emitters = (
        obj for obj in candidate_objects if getattr(obj, "_pending_domain_events", None)
    )

    for obj in emitters:
        for event_data in obj._pending_domain_events:
            # We'll use a simpler approach: serialize the entire event if possible,
            # or just use its __dict__ without the base DomainEvent fields.

            payload = {
                "_schema_version": getattr(
                    event_data, "EVENT_VERSION", 1
                ),  # DEBT-02: schema version
                **{
                    k: str(v) if isinstance(v, UUID) else v
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

    # W205 SW-A: drop the tracked emitters now their events are captured (or were
    # already empty), so the set does not accumulate across flushes in one session.
    if tracked:
        tracked.clear()

    # HIGH-W19: Store collected events on the session info dict so that
    # _persist_captured_events (after_flush_postexec) can add them without
    # triggering a recursive flush.
    if events_to_store:
        pending = session.info.setdefault("_pending_stored_events", [])
        pending.extend(events_to_store)


def _persist_captured_events(session: Session, flush_context: Any) -> None:
    """SQLAlchemy after_flush_postexec listener that writes StoredEvents to the session.

    HIGH-W19: Adding objects to the session here (after the flush has fully
    completed and the unit-of-work machinery has exited) is safe and will NOT
    cause a recursive flush, unlike doing so inside after_flush.
    """
    events_to_store = session.info.pop("_pending_stored_events", None)
    if events_to_store:
        session.add_all(events_to_store)


def capture_on_commit(session: Session) -> None:
    """W205 SW-A: before_commit catch-all that closes the systemic outbox gap.

    capture_domain_events (after_flush) only runs when a flush actually emits SQL.
    An aggregate flushed BEFORE its record_event call (e.g. a content-only message
    that repository.create_message() already flushed) leaves nothing dirty, so no
    further flush — and thus no after_flush — ever fires, and the StoredEvent was
    silently dropped (this broke the ENTIRE domain-event subsystem). before_commit
    fires on EVERY commit regardless of pending changes, so it reliably captures the
    emitters tracked by record_event on session.info["_event_emitters"]. We reuse
    the existing collect + persist functions: capture_domain_events stashes the
    StoredEvents, then _persist_captured_events adds them to the session so the
    commit's own flush writes them atomically. Idempotent with any earlier
    after_flush capture — clear_events() empties an emitter's list once captured, so
    the second pass collects nothing.
    """
    capture_domain_events(session, None)
    _persist_captured_events(session, None)


async def register_event_listeners() -> None:
    """Register domain event capturing listeners for all sessions.

    HIGH-W19 / W205 SW-A: three listeners:
      1. after_flush          — collect events from objects in this flush (no DB writes).
      2. after_flush_postexec — add StoredEvent rows after flush machinery exits,
                                preventing recursive flush.
      3. before_commit        — catch-all for events recorded after an object's last
                                flush, which after_flush never sees (no flush fires).
    """
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    sa_event.listen(Session, "after_flush", capture_domain_events)
    # HIGH-W19: persist collected events only after the flush is fully complete.
    sa_event.listen(Session, "after_flush_postexec", _persist_captured_events)
    # W205 SW-A: before_commit catch-all for events recorded after their last flush
    # (no subsequent flush fires → after_flush never sees them). See capture_on_commit.
    sa_event.listen(Session, "before_commit", capture_on_commit)
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
        #
        # HIGH-W19: asyncio.wait_for() wraps the coroutine in an internal Task but
        # does NOT cancel child tasks spawned inside handler_chain (e.g. those
        # created by execute_handlers). Those tasks become orphaned when the
        # wait_for timeout fires. Instead: create an explicit Task, wait on it with
        # asyncio.wait(), and cancel it explicitly if the deadline is exceeded.
        chain_task = asyncio.create_task(handler_chain(event))
        try:
            _done, pending = await asyncio.wait({chain_task}, timeout=10.0)
            if pending:
                # Timeout — cancel the task (and, transitively, any tasks it awaited)
                chain_task.cancel()
                try:
                    await chain_task
                except asyncio.CancelledError, Exception:  # noqa: S110  # RZ-27-01
                    pass
                logger.error(
                    "Event production timed out (10s)",
                    extra={
                        "event_type": event_type,
                        "event_id": event.event_id,
                    },
                )
            elif chain_task.exception() is not None:
                # Propagate unexpected exceptions that escaped _safe_handle
                raise chain_task.exception()  # type: ignore[misc]
        except asyncio.CancelledError:
            chain_task.cancel()
            raise

    async def _safe_handle(self, handler: EventHandler, event: DomainEvent) -> None:
        """Execute handler with error protection and optional DLQ."""
        try:
            await handler(event)
        except Exception as e:  # RZ-22-01-JUSTIFIED: handler-nak — catches handler errors, routes to DLQ (reviewed TD-27-04)
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
                except Exception as dlq_err:  # RZ-22-01-JUSTIFIED: handler-nak — critical fallback when DLQ itself fails (reviewed TD-27-04)
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
    "NotificationsRequested",
    "UserCreated",
    "UserDeleted",
    "UserLoggedIn",
    "UserUpdated",
    "capture_domain_events",
    "event_bus",
    "register_domain_event",
    "register_event_listeners",
]
