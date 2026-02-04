import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import async_session
from app.core.events import DomainEvent, EventMetadata, event_bus
from app.models.domain_events import StoredEvent

logger = logging.getLogger(__name__)


class OutboxWorker:
    """
    Worker that picks up unprocessed StoredEvents and publishes them
    to the local event bus.
    """

    def __init__(
        self, poll_interval: float = 1.0, batch_size: int = 10, max_retries: int = 5
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._is_running = False

    async def run_forever(self):
        self._is_running = True
        logger.info("OutboxWorker started")
        while self._is_running:
            try:
                processed = await self.process_batch()
                if processed == 0:
                    await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception("Error in OutboxWorker loop")
                await asyncio.sleep(self.poll_interval * 2)

    async def stop(self):
        self._is_running = False

    async def process_batch(self) -> int:
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
                return 0

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
