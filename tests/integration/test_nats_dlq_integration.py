"""Integration tests for transactional outbox worker and NATS DLQ failovers.

Verifies that the OutboxWorker correctly processes pending events, dispatches them
to the event bus, and moves persistent failures to the Dead Letter Queue (FailedOutboxEvent)
after exhausting max retry attempts.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import ClassVar

import pytest
from sqlalchemy import select
from testcontainers.core.container import DockerContainer

from app.core.config import settings
from app.core.database import async_session
from app.core.events import DomainEvent, event_bus, register_domain_event
from app.models.domain_events import StoredEvent
from app.models.failed_outbox_events import FailedOutboxEvent
from app.workers.outbox import OutboxWorker

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
pytestmark = pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run")


@register_domain_event
@dataclass
class NatsDlqIntegrationTestEvent(DomainEvent):
    message_content: str = "default_content"
    EVENT_TYPE: ClassVar[str] = "nats_dlq_integration.test_event"


@pytest.fixture(scope="module")
def nats_server():
    # Enforce JetStream enabled via the "-js" container command
    with (
        DockerContainer(
            "nats:2.10.25-alpine@sha256:3290c829aa05ddd4da12026783ccaff86f3fbc1f0551722908a934c293cd6228"
        )
        .with_exposed_ports(4222)
        .with_command("-js") as nats
    ):
        yield nats


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
async def test_nats_dlq_integration_flow(nats_server, db_session) -> None:
    port = nats_server.get_exposed_port(4222)
    host = nats_server.get_container_host_ip()
    nats_url = f"nats://{host}:{port}"

    original_nats_url = settings.nats_url
    settings.nats_url = nats_url

    # Register failing middleware on event_bus
    async def failing_middleware(event, next_handler) -> None:
        if (
            event.event_type == "nats_dlq_integration.test_event"
            and getattr(event, "message_content", "") == "failing_payload"
        ):
            raise RuntimeError("simulated middleware failure")
        await next_handler(event)

    event_bus.add_middleware(failing_middleware)

    try:
        from app.core.nats_broker import NatsTaskBroker

        broker = NatsTaskBroker()
        await broker.connect()
        assert broker.is_connected

        # 1. Case A: Happy path
        happy_called = asyncio.Event()

        async def happy_handler(event: NatsDlqIntegrationTestEvent) -> None:
            happy_called.set()

        event_bus.subscribe("nats_dlq_integration.test_event", happy_handler)

        happy_se = StoredEvent(
            id=uuid.uuid4(),
            event_type="nats_dlq_integration.test_event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-100",
            payload={"message_content": "happy_payload"},
            status="pending",
            aggregate_id_uuid=uuid.uuid4(),
            sequence_number=1,
        )
        db_session.add(happy_se)
        await db_session.commit()
        await db_session.close()  # Close session to release all locks/connections

        worker = OutboxWorker(poll_interval=0.1, batch_size=5, max_retries=3)
        processed = await worker.process_batch()
        assert processed > 0

        # Wait and verify happy_handler ran successfully
        await asyncio.wait_for(happy_called.wait(), timeout=2.0)
        assert happy_called.is_set()

        # Query using a fresh session to get the committed status
        async with async_session() as temp_db:
            stmt = select(StoredEvent).where(StoredEvent.id == happy_se.id)
            res = await temp_db.execute(stmt)
            happy_db_event = res.scalar_one()
            assert happy_db_event.processed_at is not None
            assert happy_db_event.error_count == 0

        event_bus.unsubscribe("nats_dlq_integration.test_event", happy_handler)

        # 2. Case B: DLQ failover path
        async def dummy_handler(event: NatsDlqIntegrationTestEvent) -> None:
            pass

        event_bus.subscribe("nats_dlq_integration.test_event", dummy_handler)

        failing_se = StoredEvent(
            id=uuid.uuid4(),
            event_type="nats_dlq_integration.test_event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-200",
            payload={"message_content": "failing_payload"},
            status="pending",
            aggregate_id_uuid=uuid.uuid4(),
            sequence_number=2,
        )
        # Get a fresh connection session to insert
        async with async_session() as temp_db:
            temp_db.add(failing_se)
            await temp_db.commit()

        # Each failed dispatch consumes exactly one retry attempt.
        processed1 = await worker.process_batch()
        assert processed1 > 0

        async with async_session() as temp_db:
            stmt = select(StoredEvent).where(StoredEvent.id == failing_se.id)
            res = await temp_db.execute(stmt)
            failing_db_event = res.scalar_one()
            assert failing_db_event.error_count == 1
            assert failing_db_event.processed_at is None

        # The second failure remains retryable.
        processed2 = await worker.process_batch()
        assert processed2 > 0

        async with async_session() as temp_db:
            stmt = select(StoredEvent).where(StoredEvent.id == failing_se.id)
            res = await temp_db.execute(stmt)
            failing_db_event = res.scalar_one()
            assert failing_db_event.error_count == 2
            assert failing_db_event.processed_at is None

        # The third failed attempt reaches max_retries and is dead-lettered.
        processed3 = await worker.process_batch()
        assert processed3 > 0

        # The event should now be marked processed (dead-lettered)
        async with async_session() as temp_db:
            stmt = select(StoredEvent).where(StoredEvent.id == failing_se.id)
            res = await temp_db.execute(stmt)
            failing_db_event = res.scalar_one()
            assert failing_db_event.error_count == 3
            assert failing_db_event.processed_at is not None

        # Verify FailedOutboxEvent entry exists in DB with trace details
        async with async_session() as temp_db:
            stmt = select(FailedOutboxEvent).where(
                FailedOutboxEvent.original_event_id == failing_se.id
            )
            res = await temp_db.execute(stmt)
            dlq_event = res.scalar_one_or_none()
            assert dlq_event is not None
            assert dlq_event.event_type == "nats_dlq_integration.test_event"
            assert dlq_event.payload == {"message_content": "failing_payload"}
            assert "RuntimeError" in dlq_event.error_message
            assert "simulated middleware failure" in dlq_event.error_message

        event_bus.unsubscribe("nats_dlq_integration.test_event", dummy_handler)
        await broker._nc.close()

    finally:
        settings.nats_url = original_nats_url
        if failing_middleware in event_bus._middleware:
            event_bus._middleware.remove(failing_middleware)
