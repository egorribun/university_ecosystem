"""Branch closure tests for circuit-breaker edge paths."""

import asyncio

import pytest

import app.core.circuit_breaker as circuit_module
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerState


def test_record_success_on_open_state_does_not_reset_failure_count():
    breaker = CircuitBreaker("edge-success")
    breaker._internal_state.state = CircuitBreakerState.OPEN
    breaker._internal_state.failure_count = 3

    breaker._record_success()

    assert breaker.failure_count == 3
    assert breaker.metrics.successful_calls == 1


@pytest.mark.asyncio
async def test_aexit_does_not_record_non_exception_base_exception():
    breaker = CircuitBreaker("edge-base-exception")
    sentinel = KeyboardInterrupt()

    result = await breaker.__aexit__(KeyboardInterrupt, sentinel, None)

    assert result is False
    assert breaker.metrics.total_calls == 0


@pytest.mark.asyncio
async def test_registry_lock_double_check_observes_lock_created_inside_guard(
    monkeypatch,
):
    created = asyncio.Lock()

    class Guard:
        def __enter__(self):
            circuit_module._registry_lock = created
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(circuit_module, "_registry_lock", None)
    monkeypatch.setattr(circuit_module, "_registry_alloc_lock", Guard())

    assert circuit_module._get_registry_lock() is created
