"""
Integration test: Dishka DI lifecycle for OutboxWorker and NatsTaskBroker.

These tests verify that both APP-scoped workers are wired correctly through
the Dishka container and that their lifecycles (construction + finalization)
execute without leaking state between test runs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.di_provider import create_dishka_container
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_outbox_worker_is_scope_app_singleton() -> None:
    """The DI container returns the same OutboxWorker instance on every call."""
    container = create_dishka_container()
    try:
        first = await container.get(OutboxWorker)
        second = await container.get(OutboxWorker)
        assert first is second, "Scope.APP must return the same singleton instance"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_outbox_worker_can_start_and_stop() -> None:
    """OutboxWorker retrieved from DI starts run_forever() and stops cleanly.

    Database polling and LISTEN/NOTIFY have their own integration coverage.  Mocking
    those boundaries keeps this lifecycle contract hermetic instead of permanently
    skipping it outside PostgreSQL jobs.
    """
    import asyncio

    container = create_dishka_container()
    try:
        worker: OutboxWorker = await container.get(OutboxWorker)
        worker.process_batch = AsyncMock(return_value=0)  # type: ignore[method-assign]

        async def _listen_until_cancelled() -> None:
            await asyncio.Event().wait()

        worker._listen_loop = _listen_until_cancelled  # type: ignore[method-assign]

        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.05)
        assert worker._is_running is True

        await worker.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert worker._is_running is False
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_nats_broker_degraded_mode_on_connection_failure() -> None:
    """Dishka container does NOT raise if NATS is unavailable at startup.

    The provider catches the connection error, logs a warning, and yields the
    broker in degraded mode (not connected). This matches the production
    hardening requirement: NATS unavailability is non-fatal.
    """
    from app.core.nats_broker import NatsTaskBroker

    # Patch the connect() coroutine on the class so every instance fails.
    # Cannot patch "app.core.di_provider.asyncio.wait_for" because asyncio is
    # a local import inside the provider method, not a module-level attribute.
    with patch.object(
        NatsTaskBroker,
        "connect",
        new_callable=AsyncMock,
        side_effect=Exception("NATS unreachable"),
    ):
        container = create_dishka_container()
        try:
            broker: NatsTaskBroker = await container.get(NatsTaskBroker)
            # Container must yield a broker object regardless of connection state
            assert isinstance(broker, NatsTaskBroker)
        finally:
            await container.close()


@pytest.mark.asyncio
async def test_container_close_finalizes_nats_broker() -> None:
    """Closing the Dishka container calls NatsTaskBroker.close() exactly once."""
    from app.core.nats_broker import NatsTaskBroker

    mock_broker = MagicMock(spec=NatsTaskBroker)
    mock_broker.is_connected = False
    mock_broker.connect = AsyncMock(side_effect=Exception("no NATS"))
    mock_broker.close = AsyncMock()

    with patch("app.core.nats_broker.broker", new=mock_broker):
        container = create_dishka_container()
        try:
            await container.get(NatsTaskBroker)
        finally:
            await container.close()

    mock_broker.close.assert_awaited_once()
