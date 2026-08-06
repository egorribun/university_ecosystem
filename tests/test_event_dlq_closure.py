"""Branch closure tests for in-memory DeadLetterQueue recovery paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.event_dlq import DeadLetterQueue, FailedEvent


def _event(event_id="event-1", event_type="test.event"):
    return SimpleNamespace(event_id=event_id, event_type=event_type)


class _Circuit:
    def __init__(self, state="CLOSED", allow=True):
        self.state = SimpleNamespace(name=state)
        self.allow_request = MagicMock(return_value=allow)
        self.add_state_listener = MagicMock()
        self.record_success = MagicMock()
        self.record_failure = MagicMock()


def test_constructor_attaches_circuit_breaker_and_exposes_state():
    circuit = _Circuit()
    bus = AsyncMock()
    dlq = DeadLetterQueue(event_bus=bus, circuit_breaker=circuit)

    assert dlq.is_replaying is False
    circuit.add_state_listener.assert_called_once()


def test_attach_circuit_breaker_without_bus_keeps_existing_bus():
    circuit = _Circuit()
    existing_bus = AsyncMock()
    dlq = DeadLetterQueue(event_bus=existing_bus)

    dlq.attach_circuit_breaker(circuit)

    assert dlq._event_bus is existing_bus


def test_recovery_callback_without_running_loop_is_deferred():
    dlq = DeadLetterQueue()
    dlq._queue.append(FailedEvent(_event(), "error", "RuntimeError"))

    dlq._on_circuit_state_change(
        SimpleNamespace(name="OPEN"), SimpleNamespace(name="CLOSED")
    )

    assert dlq.size == 1


@pytest.mark.asyncio
async def test_auto_replay_pauses_when_circuit_is_open():
    circuit = _Circuit(state="OPEN")
    bus = AsyncMock()
    dlq = DeadLetterQueue(event_bus=bus, circuit_breaker=circuit)
    await dlq.add(_event(), RuntimeError("error"))

    assert await dlq.auto_replay() == (0, 0)
    bus.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_replay_breaks_on_empty_batch():
    bus = AsyncMock()
    dlq = DeadLetterQueue(event_bus=bus)
    await dlq.add(_event(), RuntimeError("error"))

    assert await dlq.auto_replay(batch_size=0) == (0, 0)
    assert dlq.size == 1


@pytest.mark.asyncio
async def test_auto_replay_stops_when_circuit_rejects_item():
    circuit = _Circuit(allow=False)
    bus = AsyncMock()
    dlq = DeadLetterQueue(event_bus=bus, circuit_breaker=circuit)
    await dlq.add(_event(), RuntimeError("error"))

    assert await dlq.auto_replay(rate_limit_delay=0) == (0, 0)
    bus.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_replay_failure_without_delays_records_circuit_failure():
    circuit = _Circuit()
    bus = AsyncMock()
    bus.publish.side_effect = RuntimeError("still broken")
    dlq = DeadLetterQueue(event_bus=bus, circuit_breaker=circuit)
    await dlq.add(_event(), RuntimeError("initial"))

    assert await dlq.auto_replay(
        max_retries=1,
        base_backoff=0,
        jitter=0,
        rate_limit_delay=0,
    ) == (0, 1)
    circuit.record_failure.assert_called_once()
    assert dlq.size == 0


@pytest.mark.asyncio
async def test_remove_returns_false_for_unknown_event():
    dlq = DeadLetterQueue()
    await dlq.add(_event("first"), RuntimeError("error"))
    await dlq.add(_event("second"), RuntimeError("error"))

    assert await dlq.remove("second") is True
    assert await dlq.remove("missing") is False
