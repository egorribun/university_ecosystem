from __future__ import annotations

import asyncio
import os
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

import asyncpg
from opentelemetry import trace
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import async_session
from app.core.events import EventMetadata, event_bus
from app.models.domain_events import StoredEvent

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# ── MOD-04 (audit 2026-03-14): Prometheus metrics for outbox observability ─────
# Module-level singletons; Prometheus scrapes /metrics on each poll cycle.


def _get_or_create_metric(
    cls: Any, name: str, documentation: str, **kwargs: Any
) -> Any:
    if cls is None:
        return None
    if (
        REGISTRY
        and hasattr(REGISTRY, "_names_to_collectors")
        and name in REGISTRY._names_to_collectors
    ):
        return REGISTRY._names_to_collectors[name]
    try:
        return cls(name, documentation, **kwargs)
    except ValueError:
        if (
            REGISTRY
            and hasattr(REGISTRY, "_names_to_collectors")
            and name in REGISTRY._names_to_collectors
        ):
            return REGISTRY._names_to_collectors[name]
        raise


OUTBOX_EVENTS_PROCESSED = _get_or_create_metric(
    Counter,
    "outbox_events_processed_total",
    "Total outbox events processed",
    labelnames=["event_type", "status"],  # status: success | failed | dead_lettered
)
OUTBOX_PROCESSING_DURATION = _get_or_create_metric(
    Histogram,
    "outbox_event_processing_duration_seconds",
    "Wall-clock time to dispatch a single outbox event",
    labelnames=["event_type"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
)
OUTBOX_PENDING_EVENTS = _get_or_create_metric(
    Gauge,
    "outbox_pending_events_total",
    "Current number of pending (unprocessed) outbox events — updated each poll cycle",
)
OUTBOX_DLQ_TOTAL = _get_or_create_metric(
    Counter,
    "outbox_dlq_events_total",
    "Total events permanently moved to the Dead Letter Queue",
    labelnames=["event_type"],
)


class OutboxWorker:
    """
    Worker that picks up unprocessed StoredEvents and publishes them
    to the local event bus.

    Uses Reactive CDC (LISTEN/NOTIFY) to minimize latency and DB load. (Audit 3.2)
    """

    CHANNEL = "outbox_events"

    def __init__(
        self,
        poll_interval: float = 5.0,
        batch_size: int = 20,
        max_retries: int = 5,
        heartbeat_path: Path | None = None,
        heartbeat_interval: float = 5.0,
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.heartbeat_path = heartbeat_path
        self.heartbeat_interval = heartbeat_interval
        self._is_running = False
        self._wakeup_event = asyncio.Event()

    async def run_forever(self) -> None:
        self._is_running = True
        logger.info("OutboxWorker started (Reactive Mode)")

        auxiliary_tasks = [asyncio.create_task(self._listen_loop())]
        if self.heartbeat_path is not None:
            auxiliary_tasks.append(asyncio.create_task(self._heartbeat_loop()))

        try:
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
                except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — top-level worker loop must not crash on any error (reviewed TD-27-04)
                    logger.exception("Error in OutboxWorker loop")
                    await asyncio.sleep(self.poll_interval)
        finally:
            # Always cancel auxiliary tasks so the raw asyncpg LISTEN connection
            # is closed and the standalone heartbeat stops during shutdown.
            # Snapshot the collection before cancellation so the exact task set
            # is also the set awaited below, even if a future shutdown hook
            # mutates the working list.
            tasks_to_shutdown = tuple(auxiliary_tasks)
            for task in tasks_to_shutdown:
                task.cancel()
            await asyncio.gather(*tasks_to_shutdown, return_exceptions=True)

    async def _heartbeat_loop(self) -> None:
        """Record event-loop progress for the standalone container healthcheck."""
        heartbeat_path = self.heartbeat_path
        if heartbeat_path is None:
            return
        while self._is_running:
            heartbeat_path.write_text(str(time.time_ns()), encoding="ascii")
            await asyncio.sleep(self.heartbeat_interval)

    async def _listen_loop(self) -> None:
        """Listen for PostgreSQL NOTIFY events to wake up the worker."""
        # TD-013 (audit 2026-03-04): use urlparse instead of str.replace() to
        # safely convert the DSN scheme. str.replace() silently produced a
        # broken DSN if the asyncpg dialect marker appeared multiple times or
        # was absent (e.g. plain postgresql:// DSNs used in some envs).
        parsed = urlparse(str(settings.database_url))
        # asyncpg accepts 'postgres://' or 'postgresql://' — normalise to the
        # canonical form it uses internally.
        normalised_scheme = parsed.scheme.replace("+asyncpg", "")
        dsn = urlunparse(parsed._replace(scheme=normalised_scheme))

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
            except (
                OSError,
                ConnectionError,
            ) as e:  # RZ-22-01: narrowed — DB/network reconnect
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
                # DEBT-01: Use DISTINCT ON (aggregate_id_uuid) on PostgreSQL to
                # guarantee per-aggregate causal ordering when running multiple
                # workers with skip_locked=True.  Each worker picks at most one
                # pending event per aggregate (the one with the lowest
                # sequence_number / created_at), so events for the same aggregate
                # are never processed out of order by parallel workers.
                # Falls back to the simple created_at ordering for SQLite (CI).
                stmt = (
                    select(StoredEvent)
                    .where(StoredEvent.processed_at.is_(None))
                    .where(StoredEvent.error_count < self.max_retries)
                    .order_by(
                        StoredEvent.aggregate_id_uuid,
                        StoredEvent.sequence_number,
                        StoredEvent.created_at,
                    )
                    .limit(self.batch_size)
                    .with_for_update(skip_locked=True)
                )
                result = await db.execute(stmt)
                events = result.scalars().all()

                # MOD-04: Update pending gauge once per batch cycle (cheap COUNT).
                pending_count_result = await db.execute(
                    select(func.count())
                    .select_from(StoredEvent)
                    .where(StoredEvent.processed_at.is_(None))
                )
                OUTBOX_PENDING_EVENTS.set(pending_count_result.scalar_one() or 0)

                if not events:
                    span.set_attribute("outbox.events_count", 0)
                    return 0

                span.set_attribute("outbox.events_count", len(events))
                for se in events:
                    _t0 = time.perf_counter()
                    try:
                        await self._dispatch_event(se)
                        se.processed_at = datetime.now(UTC)
                        # MOD-04: record success latency + count
                        OUTBOX_PROCESSING_DURATION.labels(
                            event_type=se.event_type
                        ).observe(time.perf_counter() - _t0)
                        OUTBOX_EVENTS_PROCESSED.labels(
                            event_type=se.event_type, status="success"
                        ).inc()
                    except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — catch-all for dispatch errors, increments retry counter (reviewed TD-27-04)
                        se.error_count += 1
                        last_error = (
                            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                        )
                        # Store first 500 chars of error for audit trail
                        se.last_error = last_error[:500]
                        # MOD-08: Move to DLQ after max_retries instead of
                        # silently abandoning the event.
                        if se.error_count >= self.max_retries:
                            await self._move_to_dlq(db, se, last_error)
                            # MOD-04: DLQ counter (also tracked in _move_to_dlq log)
                            OUTBOX_DLQ_TOTAL.labels(event_type=se.event_type).inc()
                            OUTBOX_EVENTS_PROCESSED.labels(
                                event_type=se.event_type, status="dead_lettered"
                            ).inc()
                        else:
                            logger.error(
                                "Failed to process outbox event",
                                exc_info=True,
                                extra={
                                    "event_id": str(se.id),
                                    "event_type": se.event_type,
                                    "error_count": se.error_count,
                                },
                            )
                            OUTBOX_EVENTS_PROCESSED.labels(
                                event_type=se.event_type, status="failed"
                            ).inc()

                await db.commit()
                return len(events)

    async def _move_to_dlq(
        self, db: AsyncSession, se: StoredEvent, last_error: str
    ) -> None:
        """Move an event that exceeded max_retries to the Dead Letter Queue.

        MOD-08 (audit 2026-03-14): Provides visibility into undeliverable events
        instead of silently abandoning them after max retries.
        """
        from app.models.failed_outbox_events import FailedOutboxEvent

        dlq_entry = FailedOutboxEvent(
            original_event_id=se.id,
            event_type=se.event_type,
            aggregate_type=se.aggregate_type,
            aggregate_id=se.aggregate_id,
            payload=se.payload or {},
            error_message=last_error[:2000],  # Truncate to prevent huge rows
            retry_count=se.error_count,
            failed_at=datetime.now(UTC),
        )
        db.add(dlq_entry)
        se.processed_at = datetime.now(UTC)  # Mark as processed (dead-lettered)
        logger.error(
            "OutboxWorker: event moved to DLQ after %d retries",
            se.error_count,
            extra={
                "event_id": str(se.id),
                "event_type": se.event_type,
                "dlq_entry_id": str(dlq_entry.id),
            },
        )

    async def _dispatch_event(self, se: StoredEvent) -> None:
        """
        Reconstruct the DomainEvent from the StoredEvent and publish it.

        HIGH-04 (audit 2026-03-11): Uses the _EVENT_REGISTRY to safely
        instantiate only registered event types. Blind setattr is prohibited
        to prevent unintended attribute injection.
        """
        from app.core.events import _EVENT_REGISTRY

        event_cls = _EVENT_REGISTRY.get(se.event_type)
        if event_cls is None:
            logger.error(
                "OutboxWorker: unknown event_type %r in stored event %s — skipping",
                se.event_type,
                se.id,
            )
            se.error_count += 1
            return

        import dataclasses

        # 1. Reconstruct using known dataclass fields only
        known_fields = {f.name for f in dataclasses.fields(event_cls)}
        safe_payload = {k: v for k, v in se.payload.items() if k in known_fields}

        try:
            event = event_cls(**safe_payload)

            # 2. Restore metadata if present
            if se.metadata_:
                event.event_id = se.metadata_.get("event_id", event.event_id)
                event.metadata = EventMetadata(
                    correlation_id=se.metadata_.get("correlation_id"),
                    user_id=se.metadata_.get("user_id"),
                )

            with tracer.start_as_current_span("outbox.dispatch_event") as span:
                span.set_attribute("outbox.event_type", se.event_type)
                span.set_attribute("outbox.stored_event_id", str(se.id))
                # MOD-01 (audit 2026-03-14): aggregate attributes enable trace
                # filtering by aggregate ID (e.g. "show all events for Chat X")
                # without scanning the trace body.
                if se.aggregate_id_uuid is not None:
                    span.set_attribute("outbox.aggregate_id", str(se.aggregate_id_uuid))
                if se.sequence_number is not None:
                    span.set_attribute("outbox.sequence_number", se.sequence_number)
                span.set_attribute("outbox.aggregate_type", se.aggregate_type or "")
                await event_bus.publish(event)

        except Exception as e:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — logs then re-raises for caller retry logic (reviewed TD-27-04)
            logger.error("Failed to reconstruct event %s: %s", se.id, e)
            se.error_count += 1
            raise


async def _wait_for_signals(stop_event: asyncio.Event) -> None:
    import signal

    loop = asyncio.get_running_loop()
    handled_signals = [signal.SIGINT, signal.SIGTERM]

    def _handler(*_: object) -> None:
        stop_event.set()

    for sig in handled_signals:
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    await stop_event.wait()


async def main() -> None:
    from app.core.config import settings
    from app.core.database import init_database, wait_db
    from app.core.events import register_event_listeners
    from app.core.nats_broker import broker as nats_broker
    from app.services.event_handlers import configure_event_handlers

    init_database()
    await wait_db(max_attempts=10)

    await register_event_listeners()
    configure_event_handlers()
    await nats_broker.connect()

    runtime_dir = Path(
        os.environ.get("OUTBOX_WORKER_RUNTIME_DIR") or tempfile.gettempdir()
    )
    runtime_dir.mkdir(parents=True, exist_ok=True)
    pid_path = runtime_dir / "worker.pid"
    heartbeat_path = runtime_dir / "worker.heartbeat"
    pid_path.write_text(str(os.getpid()), encoding="ascii")

    worker = OutboxWorker(
        poll_interval=settings.outbox_poll_interval_seconds,
        batch_size=settings.outbox_batch_size,
        max_retries=settings.outbox_max_retries,
        heartbeat_path=heartbeat_path,
    )

    stop_event = asyncio.Event()

    try:
        async with asyncio.TaskGroup() as tg:
            worker_task = tg.create_task(worker.run_forever())
            tg.create_task(_wait_for_signals(stop_event))

            await stop_event.wait()
            await worker.stop()
            worker_task.cancel()
    finally:
        await nats_broker.close()
        pid_path.unlink(missing_ok=True)
        heartbeat_path.unlink(missing_ok=True)

    logger.info("Outbox worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
