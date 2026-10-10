"""An exhausted task timeout preserves a replayable dead-letter record."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core import database, nats_broker
from app.models.dead_letter import DeadLetterJob, JobStatus


@pytest.mark.asyncio
async def test_exhausted_timeout_commits_task_and_reason_before_terminating(
    db_session, monkeypatch
):
    broker = nats_broker.NatsTaskBroker()
    task_name = "contracts.timeout.persist"
    task_payload = {
        "id": "timeout-persistence-task",
        "name": task_name,
        "args": [42, "pending content"],
        "kwargs": {"locale": "ru", "notify": True},
        "trace_context": {},
    }
    message = AsyncMock()
    message.data = json.dumps(task_payload).encode()
    message.metadata = SimpleNamespace(num_delivered=nats_broker._MAX_DELIVERIES)
    subscription = AsyncMock()
    subscription.fetch.side_effect = [[message], asyncio.CancelledError()]
    transport = AsyncMock()
    transport.pull_subscribe.return_value = subscription
    broker._js = transport
    received = []
    committed = []

    @broker.task(name=task_name)
    async def waiting_handler(*args, **kwargs):
        received.append((args, kwargs))
        await asyncio.Event().wait()

    async def observe_committed_record():
        # A second session observes persistence before transport termination.
        async with database.async_session() as observer:
            row = (
                await observer.execute(
                    select(DeadLetterJob).where(DeadLetterJob.job_type == task_name)
                )
            ).scalar_one()
            committed.append(
                (
                    json.loads(row.payload),
                    row.error_message,
                    row.status,
                    row.retry_count,
                )
            )

    message.term.side_effect = observe_committed_record
    monkeypatch.setattr(nats_broker, "_app", None)
    # Trigger the existing timeout context at the handler's first suspension;
    # no background task or wall-clock sleep is needed by this fixture.
    monkeypatch.setattr(nats_broker, "_DEFAULT_TASK_TIMEOUT_S", 0)
    with pytest.raises(asyncio.CancelledError):
        await broker.run_worker()

    assert received == [((42, "pending content"), {"locale": "ru", "notify": True})]
    message.term.assert_awaited_once_with()
    message.ack.assert_not_awaited()
    message.nak.assert_not_awaited()
    # Assertions stay outside the worker's exception-recovery boundary.
    assert len(committed) == 1
    payload, reason, status, retry_count = committed[0]
    assert payload == {
        "args": [42, "pending content"],
        "kwargs": {"locale": "ru", "notify": True},
    }
    assert reason and "timed out" in reason
    assert status == JobStatus.PENDING.value
    assert retry_count == 0
