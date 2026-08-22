"""Closure tests for outbox metrics and standalone worker lifecycle."""

import os
from pathlib import Path
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
async def test_outbox_main_uses_reactive_worker_when_legacy_cdc_flag_is_set(
    monkeypatch,
):
    await _prepare_outbox_main(monkeypatch)
    run_forever = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(outbox.OutboxWorker, "run_forever", run_forever)
    monkeypatch.setattr(outbox.OutboxWorker, "stop", stop)

    with (
        patch.dict("os.environ", {"ENABLE_CDC_OUTBOX": "true"}),
        patch("app.workers.cdc_outbox.CdcOutboxWorker") as constructor,
        patch("app.core.nats_broker.broker.connect", new_callable=AsyncMock),
        patch("app.core.nats_broker.broker.close", new_callable=AsyncMock),
    ):
        await outbox.main()

    constructor.assert_not_called()
    run_forever.assert_awaited_once()
    stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_main_connects_and_closes_nats(monkeypatch):
    await _prepare_outbox_main(monkeypatch)
    run_forever = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(outbox.OutboxWorker, "run_forever", run_forever)
    monkeypatch.setattr(outbox.OutboxWorker, "stop", stop)

    with (
        patch.object(
            outbox,
            "settings",
            SimpleNamespace(
                outbox_poll_interval_seconds=1.0,
                outbox_batch_size=2,
                outbox_max_retries=3,
            ),
        ),
        patch("app.core.nats_broker.broker.connect", new_callable=AsyncMock) as connect,
        patch("app.core.nats_broker.broker.close", new_callable=AsyncMock) as close,
    ):
        await outbox.main()

    connect.assert_awaited_once()
    close.assert_awaited_once()
    run_forever.assert_awaited_once()
    stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_main_records_current_process_pid(monkeypatch, tmp_path: Path):
    await _prepare_outbox_main(monkeypatch)
    # Exercise the recursive directory creation contract.  ``parents=None``
    # is accepted by ``Path.mkdir`` when the directory already exists, but it
    # fails for a fresh nested runtime path and would leave the worker without
    # its liveness markers.
    runtime_dir = tmp_path / "nested" / "runtime"
    monkeypatch.setenv("OUTBOX_WORKER_RUNTIME_DIR", str(runtime_dir))
    # Preserve the runtime markers long enough to assert their contents. The
    # production finally block still invokes unlink for both marker files.
    unlink_calls: list[Path] = []

    def record_unlink(path: Path, missing_ok: bool = False) -> None:
        del missing_ok
        unlink_calls.append(path)

    monkeypatch.setattr(Path, "unlink", record_unlink)
    write_calls: list[tuple[Path, str, str | None]] = []
    original_write_text = Path.write_text

    def record_write(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        write_calls.append((path, data, encoding))
        return original_write_text(
            path, data, encoding=encoding, errors=errors, newline=newline
        )

    monkeypatch.setattr(Path, "write_text", record_write)

    with (
        patch.object(
            outbox,
            "settings",
            SimpleNamespace(
                outbox_poll_interval_seconds=1.0,
                outbox_batch_size=2,
                outbox_max_retries=3,
            ),
        ),
        patch.object(outbox.OutboxWorker, "run_forever", new_callable=AsyncMock),
        patch.object(outbox.OutboxWorker, "stop", new_callable=AsyncMock),
        patch("app.core.nats_broker.broker.connect", new_callable=AsyncMock),
        patch("app.core.nats_broker.broker.close", new_callable=AsyncMock),
    ):
        await outbox.main()

    assert (runtime_dir / "worker.pid").read_text(encoding="ascii") == str(os.getpid())
    assert [
        encoding for path, _data, encoding in write_calls if path.name == "worker.pid"
    ] == ["ascii"]
    assert [path.name for path in unlink_calls] == ["worker.pid", "worker.heartbeat"]


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


@pytest.mark.asyncio
async def test_outbox_heartbeat_records_event_loop_progress(
    tmp_path: Path, monkeypatch
) -> None:
    heartbeat_path = tmp_path / "worker.heartbeat"
    worker = outbox.OutboxWorker(heartbeat_path=heartbeat_path)
    worker._is_running = True

    async def stop_after_first_heartbeat(_seconds: float) -> None:
        worker._is_running = False

    monkeypatch.setattr(outbox.asyncio, "sleep", stop_after_first_heartbeat)

    await worker._heartbeat_loop()

    assert heartbeat_path.is_file()
    assert heartbeat_path.read_text(encoding="ascii").strip().isdigit()


@pytest.mark.asyncio
async def test_outbox_heartbeat_writes_with_ascii_encoding(monkeypatch) -> None:
    heartbeat_path = MagicMock()
    worker = outbox.OutboxWorker(heartbeat_path=heartbeat_path)
    worker._is_running = True

    async def stop_after_first_heartbeat(_seconds: float) -> None:
        worker._is_running = False

    monkeypatch.setattr(outbox.asyncio, "sleep", stop_after_first_heartbeat)

    await worker._heartbeat_loop()

    heartbeat_path.write_text.assert_called_once()
    assert heartbeat_path.write_text.call_args.kwargs["encoding"] == "ascii"
