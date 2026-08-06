"""
Dead Letter Queue for failed domain events.

Provides storage and replay capabilities for events that failed processing.
"""

from __future__ import annotations

import asyncio
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.events import DomainEvent, EventBus
    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker

logger = get_logger(__name__)
_dlq_tasks: set[asyncio.Task[Any]] = set()


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
    - Automated recovery replay engine with circuit breaker listener,
      thundering herd prevention, rate limiting, and exponential backoff.
    """

    def __init__(
        self,
        max_size: int = 1000,
        *,
        event_bus: EventBus | None = None,
        circuit_breaker: RedisCircuitBreaker | None = None,
    ) -> None:
        """
        Initialize the DLQ.

        Args:
            max_size: Maximum number of events to store. Oldest events
                      are dropped when limit is reached.
            event_bus: Optional EventBus instance for replay.
            circuit_breaker: Optional RedisCircuitBreaker instance for auto-recovery.
        """
        logger.warning(
            "DeadLetterQueue is using in-memory storage — all events will be "
            "lost on process restart. Consider a persistent backend for "
            "production use.",
        )
        self._queue: deque[FailedEvent] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._replay_lock = asyncio.Lock()
        self._max_size = max_size
        self._event_bus = event_bus
        self._circuit_breaker: RedisCircuitBreaker | None = None
        self._is_replaying = False
        self._last_replay_at: datetime | None = None
        self._total_replayed_success = 0
        self._total_replayed_failed = 0

        if circuit_breaker is not None:
            self.attach_circuit_breaker(circuit_breaker, event_bus)

    @property
    def size(self) -> int:
        """Return current number of events in the queue."""
        return len(self._queue)

    @property
    def max_size(self) -> int:
        """Return maximum queue size."""
        return self._max_size

    @property
    def is_replaying(self) -> bool:
        """Return whether automated replay is currently executing."""
        return self._is_replaying

    def attach_circuit_breaker(
        self,
        circuit_breaker: RedisCircuitBreaker,
        bus: EventBus | None = None,
    ) -> None:
        """Attach a circuit breaker to trigger automated replay on recovery."""
        self._circuit_breaker = circuit_breaker
        if bus is not None:
            self._event_bus = bus

        circuit_breaker.add_state_listener(self._on_circuit_state_change)
        logger.info(
            "Attached RedisCircuitBreaker listener to in-memory DeadLetterQueue"
        )

    def _on_circuit_state_change(
        self,
        old_state: CircuitState,
        new_state: CircuitState,
    ) -> None:
        """Callback triggered when circuit breaker state changes."""
        # Trigger recovery replay when circuit moves out of OPEN (HALF_OPEN or CLOSED)
        if getattr(new_state, "name", str(new_state)) in ("HALF_OPEN", "CLOSED"):
            if len(self._queue) > 0:
                logger.info(
                    "Circuit breaker recovered (%s -> %s). Triggering automated DLQ replay (%d queued events).",
                    getattr(old_state, "name", str(old_state)),
                    getattr(new_state, "name", str(new_state)),
                    len(self._queue),
                )
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(self.auto_replay())
                    _dlq_tasks.add(task)
                    task.add_done_callback(_dlq_tasks.discard)
                except RuntimeError:
                    # No running loop, will be picked up on next active cycle
                    pass

    async def auto_replay(
        self,
        bus: EventBus | None = None,
        *,
        batch_size: int = 20,
        max_retries: int = 3,
        base_backoff: float = 0.1,
        max_backoff: float = 5.0,
        jitter: float = 0.1,
        rate_limit_delay: float = 0.01,
        force: bool = False,
    ) -> tuple[int, int]:
        """
        Automated recovery replay engine.

        Features:
        - Thundering herd prevention via asyncio lock
        - Rate-limited batch processing
        - Exponential backoff with jitter on failures
        - Circuit breaker monitoring during replay

        Returns:
            Tuple of (successful_count, failed_count)
        """
        target_bus = bus or self._event_bus
        if not target_bus:
            logger.warning("Auto-replay requested but no EventBus is attached")
            return (0, 0)

        # Thundering herd prevention: if replay is already in progress, skip or return
        if self._replay_lock.locked() and not force:
            logger.info(
                "Auto-replay already in progress; skipping trigger (thundering herd prevention)"
            )
            return (0, 0)

        async with self._replay_lock:
            self._is_replaying = True
            self._last_replay_at = datetime.now(UTC)
            total_success = 0
            total_failed = 0

            try:
                while len(self._queue) > 0:
                    if self._circuit_breaker and not force:
                        if (
                            getattr(
                                self._circuit_breaker.state,
                                "name",
                                str(self._circuit_breaker.state),
                            )
                            == "OPEN"
                        ):
                            logger.warning(
                                "Circuit breaker is OPEN during auto-replay; pausing replay engine"
                            )
                            break

                    async with self._lock:
                        batch = list(self._queue)[:batch_size]

                    if not batch:
                        break

                    batch_success = 0
                    batch_failed = 0
                    circuit_paused = False

                    for failed in batch:
                        if self._circuit_breaker and not force:
                            if not self._circuit_breaker.allow_request():
                                circuit_paused = True
                                break

                        try:
                            await target_bus.publish(failed.event)
                            await self.remove(failed.event.event_id)
                            batch_success += 1
                            self._total_replayed_success += 1
                            if self._circuit_breaker:
                                self._circuit_breaker.record_success()
                        except Exception as exc:  # RZ-22-01-JUSTIFIED: Replay handler error must be captured for exponential backoff update
                            batch_failed += 1
                            self._total_replayed_failed += 1
                            failed.retry_count += 1

                            backoff = min(
                                base_backoff * (2**failed.retry_count)
                                + random.uniform(0, jitter),  # noqa: S311 # nosec B311
                                max_backoff,
                            )
                            if failed.retry_count >= max_retries:
                                await self.remove(failed.event.event_id)
                                logger.error(
                                    "Event %s permanently failed DLQ replay after %d retries: %s",
                                    failed.event.event_id,
                                    failed.retry_count,
                                    exc,
                                )

                            if self._circuit_breaker:
                                self._circuit_breaker.record_failure()

                            if backoff > 0:
                                await asyncio.sleep(backoff)

                        if rate_limit_delay > 0:
                            await asyncio.sleep(rate_limit_delay)

                    total_success += batch_success
                    total_failed += batch_failed

                    if circuit_paused:
                        # The queue is unchanged when the breaker rejects a
                        # request; leave the outer loop or it will spin forever.
                        break

                    if batch_failed > 0 and not force:
                        # Pause replay run on batch failure to allow backoff
                        break
            finally:
                self._is_replaying = False

            return (total_success, total_failed)

    async def get_replay_status(self) -> dict[str, Any]:
        """Get metrics on replay status, queue depth, and auto-replay configurations."""
        async with self._lock:
            return {
                "size": len(self._queue),
                "max_size": self._max_size,
                "is_replaying": self._is_replaying,
                "auto_replay_enabled": self._circuit_breaker is not None,
                "last_replay_at": (
                    self._last_replay_at.isoformat() if self._last_replay_at else None
                ),
                "total_replayed_success": self._total_replayed_success,
                "total_replayed_failed": self._total_replayed_failed,
            }

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
        success_ids: set[str] = set()

        for failed in events_to_replay:
            try:
                await bus.publish(failed.event)
                success_count += 1
                success_ids.add(failed.event.event_id)
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
