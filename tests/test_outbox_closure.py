"""Closure tests for outbox metric registration and CDC worker selection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.outbox as outbox


def test_get_or_create_metric_handles_none_and_existing_registry_entry():
    assert outbox._get_or_create_metric(None, "unused", "unused") is None
    existing = outbox.OUTBOX_EVENTS_PROCESSED

    assert (
        outbox._get_or_create_metric(
            MagicMock, "outbox_events_processed_total", "unused"
        )
        is existing
    )


def test_get_or_create_metric_reuses_metric_after_registration_race():
    existing = object()
    registry = SimpleNamespace(_names_to_collectors={})

    def register_then_raise(name, _documentation):
        registry._names_to_collectors[name] = existing
        raise ValueError("already registered")

    constructor = MagicMock(side_effect=register_then_raise)

    with patch.object(outbox, "REGISTRY", registry):
        result = outbox._get_or_create_metric(constructor, "race_metric", "unused")

    assert result is existing
    constructor.assert_called_once_with("race_metric", "unused")


def test_get_or_create_metric_reraises_unrecoverable_registration_error():
    registry = SimpleNamespace(_names_to_collectors={})
    constructor = MagicMock(side_effect=ValueError("invalid metric"))

    with patch.object(outbox, "REGISTRY", registry), pytest.raises(ValueError):
        outbox._get_or_create_metric(constructor, "invalid_metric", "unused")


async def _prepare_outbox_main(monkeypatch):
    monkeypatch.setattr("app.core.database.init_database", lambda: None)

    async def wait_db(*_args, **_kwargs):
        return None

    async def register_listeners():
        return None

    async def trigger_stop(stop_event):
        stop_event.set()

    monkeypatch.setattr("app.core.database.wait_db", wait_db)
    monkeypatch.setattr("app.core.events.register_event_listeners", register_listeners)
    monkeypatch.setattr(
        "app.services.event_handlers.configure_event_handlers", lambda: None
    )
    monkeypatch.setattr(outbox, "_wait_for_signals", trigger_stop)


@pytest.mark.asyncio
async def test_outbox_main_uses_cdc_worker_when_enabled(monkeypatch):
    await _prepare_outbox_main(monkeypatch)
    cdc_worker = SimpleNamespace(run_forever=AsyncMock(), stop=AsyncMock())

    with (
        patch.dict("os.environ", {"ENABLE_CDC_OUTBOX": "true"}),
        patch(
            "app.workers.cdc_outbox.CdcOutboxWorker", return_value=cdc_worker
        ) as constructor,
    ):
        await outbox.main()

    constructor.assert_called_once_with()
    cdc_worker.run_forever.assert_awaited_once()
    cdc_worker.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_main_falls_back_when_cdc_worker_initialization_fails(monkeypatch):
    await _prepare_outbox_main(monkeypatch)
    run_forever = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(outbox.OutboxWorker, "run_forever", run_forever)
    monkeypatch.setattr(outbox.OutboxWorker, "stop", stop)

    with (
        patch.dict("os.environ", {"ENABLE_CDC_OUTBOX": "true"}),
        patch(
            "app.workers.cdc_outbox.CdcOutboxWorker",
            side_effect=RuntimeError("CDC unavailable"),
        ),
        patch.object(
            outbox,
            "settings",
            SimpleNamespace(outbox_poll_interval_seconds=1.0, outbox_batch_size=2),
        ),
    ):
        await outbox.main()

    run_forever.assert_awaited_once()
    stop.assert_awaited_once()


async def test_outbox_run_forever_handles_notification_wait_timeout(monkeypatch):
    worker = outbox.OutboxWorker(poll_interval=1, batch_size=2)

    async def process_once():
        worker._is_running = False
        return 0

    worker.process_batch = process_once
    monkeypatch.setattr(worker, "_listen_loop", AsyncMock())

    async def timeout_and_close(awaitable, *, timeout):
        del timeout
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(
        outbox.asyncio,
        "wait_for",
        timeout_and_close,
    )

    await worker.run_forever()

    assert not worker._wakeup_event.is_set()
