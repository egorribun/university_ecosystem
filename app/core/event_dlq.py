"""
Dead Letter Queue for failed domain events.

Provides storage and replay capabilities for events that failed processing.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.events import DomainEvent, EventBus

logger = get_logger(__name__)


@dataclass
class FailedEvent:
    """
    Record of a failed event for the DLQ.

    Contains the original event, error details, and metadata about the failure.
    """

    event: DomainEvent
    error: str
    error_type: str
    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    handler_name: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event.event_id,
            "event_type": self.event.event_type,
            "error": self.error,
            "error_type": self.error_type,
            "failed_at": self.failed_at.isoformat(),
            "handler_name": self.handler_name,
            "retry_count": self.retry_count,
        }


class DeadLetterQueue:
    """
    In-memory Dead Letter Queue for failed events.

    Provides:
    - Storage for failed events with configurable max size
    - Retrieval and inspection of failed events
    - Replay functionality to re-process events
    - Thread-safe async operations

    Example:
        dlq = DeadLetterQueue(max_size=1000)
        await dlq.add(failed_event, ValueError("oops"))

        # Later, replay all events
        replayed = await dlq.replay(event_bus)
    """

    def __init__(self, max_size: int = 1000) -> None:
        """
        Initialize the DLQ.

        Args:
            max_size: Maximum number of events to store. Oldest events
                      are dropped when limit is reached.
        """
        # MED-W19: This DLQ is purely in-memory.  All queued events are lost on
        # process restart (deployment, crash, OOM kill).  For production
        # durability, persist failed events to a database or a NATS stream.
        logger.warning(
            "DeadLetterQueue is using in-memory storage — all events will be "
            "lost on process restart.  Consider a persistent backend for "
            "production use.",
        )
        self._queue: deque[FailedEvent] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._max_size = max_size

    @property
    def size(self) -> int:
        """Return current number of events in the queue."""
        return len(self._queue)

    @property
    def max_size(self) -> int:
        """Return maximum queue size."""
        return self._max_size

    async def add(
        self,
        event: DomainEvent,
        error: Exception,
        handler_name: str | None = None,
    ) -> None:
        """
        Add a failed event to the queue.

        Args:
            event: The domain event that failed.
            error: The exception that caused the failure.
            handler_name: Optional name of the handler that failed.
        """
        retry_count = 0
        if hasattr(event, "metadata") and hasattr(event.metadata, "retry_count"):
            retry_count = event.metadata.retry_count

        failed = FailedEvent(
            event=event,
            error=str(error),
            error_type=type(error).__name__,
            handler_name=handler_name,
            retry_count=retry_count,
        )

        async with self._lock:
            self._queue.append(failed)
            logger.warning(
                "Event added to DLQ: %s (id=%s, error=%s)",
                event.event_type,
                event.event_id,
                failed.error_type,
            )

    async def get_all(self) -> list[FailedEvent]:
        """
        Get all failed events in the queue.

        Returns a copy to prevent external modification.
        """
        async with self._lock:
            return list(self._queue)

    async def get_by_type(self, event_type: str) -> list[FailedEvent]:
        """Get failed events of a specific type."""
        async with self._lock:
            return [f for f in self._queue if f.event.event_type == event_type]

    async def clear(self) -> int:
        """
        Clear all events from the queue.

        Returns:
            Number of events cleared.
        """
        async with self._lock:
            count = len(self._queue)
            self._queue.clear()
            logger.info("DLQ cleared: %d events removed", count)
            return count

    async def remove(self, event_id: str) -> bool:
        """
        Remove a specific event from the queue.

        Args:
            event_id: The ID of the event to remove.

        Returns:
            True if event was found and removed, False otherwise.
        """
        # MED-W19: deque deletion is O(n) — both the linear scan and the
        # subsequent element shift.  For high-volume DLQs, replace self._queue
        # with a dict[str, FailedEvent] keyed on event_id to achieve O(1)
        # removal.  The deque is retained here to preserve insertion-ordered
        # iteration for replay(), but a dict preserves insertion order in
        # Python ≥ 3.7 and is a safe drop-in replacement.
        async with self._lock:
            for i, failed in enumerate(self._queue):
                if failed.event.event_id == event_id:
                    del self._queue[i]
                    logger.info("Event removed from DLQ: %s", event_id)
                    return True
            return False

    async def replay(
        self,
        bus: EventBus,
        *,
        event_type: str | None = None,
        clear_on_success: bool = True,
    ) -> tuple[int, int]:
        """
        Replay events from the DLQ.

        Args:
            bus: The EventBus to publish events to.
            event_type: Optional filter to replay only specific event types.
            clear_on_success: If True, remove successfully replayed events.

        Returns:
            Tuple of (successful_count, failed_count).
        """
        async with self._lock:
            if event_type:
                events_to_replay = [
                    f for f in self._queue if f.event.event_type == event_type
                ]
            else:
                events_to_replay = list(self._queue)

        success_count = 0
        fail_count = 0
        success_ids: list[str] = []

        for failed in events_to_replay:
            try:
                await bus.publish(failed.event)
                success_count += 1
                success_ids.append(failed.event.event_id)
                logger.info(
                    "DLQ event replayed successfully: %s",
                    failed.event.event_id,
                )
            except Exception as e:  # RZ-22-01-JUSTIFIED: handler-nak — continues replaying remaining DLQ events on failure (reviewed TD-27-04)
                fail_count += 1
                logger.error(
                    "DLQ replay failed for event %s: %s",
                    failed.event.event_id,
                    e,
                )

        # Remove successfully replayed events
        if clear_on_success and success_ids:
            async with self._lock:
                self._queue = deque(
                    (f for f in self._queue if f.event.event_id not in success_ids),
                    maxlen=self._max_size,
                )

        logger.info(
            "DLQ replay complete: %d succeeded, %d failed",
            success_count,
            fail_count,
        )
        return success_count, fail_count

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about the DLQ."""
        async with self._lock:
            events = list(self._queue)

        if not events:
            return {
                "size": 0,
                "max_size": self._max_size,
                "oldest_event": None,
                "newest_event": None,
                "by_type": {},
                "by_error": {},
            }

        by_type: dict[str, int] = {}
        by_error: dict[str, int] = {}

        for failed in events:
            by_type[failed.event.event_type] = (
                by_type.get(failed.event.event_type, 0) + 1
            )
            by_error[failed.error_type] = by_error.get(failed.error_type, 0) + 1

        return {
            "size": len(events),
            "max_size": self._max_size,
            "oldest_event": events[0].failed_at.isoformat() if events else None,
            "newest_event": events[-1].failed_at.isoformat() if events else None,
            "by_type": by_type,
            "by_error": by_error,
        }


# Global DLQ instance
dead_letter_queue = DeadLetterQueue()


__all__ = [
    "DeadLetterQueue",
    "FailedEvent",
    "dead_letter_queue",
]
