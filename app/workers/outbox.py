import asyncio
import contextlib
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
from opentelemetry import trace
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session
from app.core.events import DomainEvent, EventMetadata, event_bus
from app.models.domain_events import StoredEvent

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class OutboxWorker:
    """
    Worker that picks up unprocessed StoredEvents and publishes them
    to the local event bus.

    Uses Reactive CDC (LISTEN/NOTIFY) to minimize latency and DB load. (Audit 3.2)
    """

    CHANNEL = "outbox_events"

    def __init__(
        self, poll_interval: float = 5.0, batch_size: int = 20, max_retries: int = 5
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._is_running = False
        self._wakeup_event = asyncio.Event()

    async def run_forever(self) -> None:
        self._is_running = True
        logger.info("OutboxWorker started (Reactive Mode)")

        listen_task = asyncio.create_task(self._listen_loop())

        while self._is_running:
            try:
                processed = await self.process_batch()

                # Wait for next notification or timeout
                # We always wait if we processed all pending events or if none were found
                if processed < self.batch_size:
                    try:
                        await asyncio.wait_for(
                            self._wakeup_event.wait(), timeout=self.poll_interval
                        )
                    except TimeoutError:
                        pass
                    finally:
                        self._wakeup_event.clear()
            except Exception:
                logger.exception("Error in OutboxWorker loop")
                await asyncio.sleep(self.poll_interval)

        listen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listen_task

    async def _listen_loop(self) -> None:
        """Listen for PostgreSQL NOTIFY events to wake up the worker."""
        # asyncpg needs the DSN, strip +asyncpg for compatibility if present
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgres://")

        while self._is_running:
            try:
                conn = await asyncpg.connect(dsn)
                try:
                    await conn.add_listener(self.CHANNEL, self._on_notification)
                    logger.info(
                        "Listening for notifications on channel: %s", self.CHANNEL
                    )
                    while self._is_running:
                        # Keep connection alive
                        await asyncio.sleep(30)
                        await conn.execute("SELECT 1")
                finally:
                    await conn.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("OutboxWorker listen connection lost, retrying: %s", e)
                await asyncio.sleep(5)

    def _on_notification(self, *args: Any) -> None:
        self._wakeup_event.set()

    async def stop(self) -> None:
        self._is_running = False
        self._wakeup_event.set()

    async def process_batch(self) -> int:
        with tracer.start_as_current_span("outbox.process_batch") as span:
            async with async_session() as db:
                # Find unprocessed events or those that failed but haven't exceeded retries
                stmt = (
                    select(StoredEvent)
                    .where(StoredEvent.processed_at.is_(None))
                    .where(StoredEvent.error_count < self.max_retries)
                    .order_by(StoredEvent.created_at)
                    .limit(self.batch_size)
                    .with_for_update(skip_locked=True)
                )
                result = await db.execute(stmt)
                events = result.scalars().all()

                if not events:
                    span.set_attribute("outbox.events_count", 0)
                    return 0

                span.set_attribute("outbox.events_count", len(events))
                for se in events:
                    try:
                        # Construct DomainEvent from StoredEvent
                        # This is a bit tricky as we need the original event class.
                        # For now, we'll use a generic approach or look up by event_type.
                        # In a real system, we'd have a factory to reconstruct the event.
                        await self._dispatch_event(se)
                        se.processed_at = datetime.now(UTC)
                    except Exception:
                        logger.error(
                            "Failed to process outbox event",
                            exc_info=True,
                            extra={
                                "event_id": str(se.id),
                                "event_type": se.event_type,
                                "error_count": se.error_count + 1,
                            },
                        )
                        se.error_count += 1
                        # Store first 500 chars of error for audit trail
                        se.last_error = traceback.format_exc()[:500]

                await db.commit()
                return len(events)

    async def _dispatch_event(self, se: StoredEvent):
        # Very simple reconstruction for demonstration.
        # In a real app, this would be more robust.
        with tracer.start_as_current_span("outbox.dispatch_event") as span:
            span.set_attribute("outbox.event_type", se.event_type)
            span.set_attribute("outbox.aggregate_type", se.aggregate_type)
            span.set_attribute("outbox.aggregate_id", se.aggregate_id)

            @dataclass
            class ReconstructedEvent(DomainEvent):
                _type: str = ""

                def __post_init__(self):
                    for k, v in se.payload.items():
                        setattr(self, k, v)

                @property
                def event_type(self) -> str:
                    return self._type

            event = ReconstructedEvent(_type=se.event_type)
            if se.metadata_:
                event.event_id = se.metadata_.get("event_id", event.event_id)
                event.metadata = EventMetadata(
                    correlation_id=se.metadata_.get("correlation_id"),
                    user_id=se.metadata_.get("user_id"),
                )

            await event_bus.publish(event)
