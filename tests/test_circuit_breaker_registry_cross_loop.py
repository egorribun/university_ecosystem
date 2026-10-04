"""Cross-loop lifecycle contracts for the process-wide breaker registry."""

from __future__ import annotations

import asyncio
import threading

import pytest

import app.core.circuit_breaker as circuit_module
from app.core.circuit_breaker import CircuitBreakerState
from tests.helpers.circuit_process import assert_circuit_scenario_completes


def test_registry_contention_does_not_bind_to_a_closed_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert_circuit_scenario_completes(
        _registry_contention_does_not_bind_to_a_closed_event_loop, with_monkeypatch=True
    )
    _registry_contention_does_not_bind_to_a_closed_event_loop(monkeypatch)


def _registry_contention_does_not_bind_to_a_closed_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(circuit_module, "_registry_lock", threading.Lock())
    monkeypatch.setattr(circuit_module, "_circuit_breakers", {})

    async def contend_during_reset() -> None:
        breaker = await circuit_module.get_circuit_breaker("cross-loop-registry")
        breaker._internal_state.state = CircuitBreakerState.OPEN
        breaker._internal_state.failure_count = 3
        assert breaker._lock.acquire()
        reset_task = asyncio.create_task(circuit_module.reset_all_circuit_breakers())
        try:
            await asyncio.sleep(0)
            getter_task = asyncio.create_task(
                circuit_module.get_circuit_breaker("cross-loop-registry")
            )
            await asyncio.sleep(0)
            assert not reset_task.done()
            assert getter_task.done()
        finally:
            breaker._release_state_lock()

        await asyncio.wait_for(
            asyncio.gather(reset_task, getter_task),
            timeout=1,
        )
        assert breaker.state is CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    asyncio.run(contend_during_reset())

    async def contend_from_next_loop() -> None:
        expected = circuit_module._circuit_breakers["cross-loop-registry"]
        actual = await asyncio.wait_for(
            circuit_module.get_circuit_breaker("cross-loop-registry"),
            timeout=1,
        )
        assert actual is expected

    asyncio.run(contend_from_next_loop())


def test_cancelled_reset_keeps_registry_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_circuit_scenario_completes(
        _cancelled_reset_keeps_registry_usable, with_monkeypatch=True
    )
    _cancelled_reset_keeps_registry_usable(monkeypatch)


def _cancelled_reset_keeps_registry_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(circuit_module, "_registry_lock", threading.Lock())
    monkeypatch.setattr(circuit_module, "_circuit_breakers", {})

    async def cancel_reset_while_breaker_is_busy() -> None:
        breaker = await circuit_module.get_circuit_breaker("cancelled-reset")
        assert breaker._lock.acquire()
        reset_task = asyncio.create_task(circuit_module.reset_all_circuit_breakers())
        try:
            await asyncio.sleep(0)
            assert not reset_task.done()
            reset_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reset_task
        finally:
            breaker._release_state_lock()

        found = await asyncio.wait_for(
            circuit_module.get_circuit_breaker("cancelled-reset"),
            timeout=1,
        )
        assert found is breaker

    asyncio.run(cancel_reset_while_breaker_is_busy())
