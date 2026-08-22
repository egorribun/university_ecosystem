"""Fast, deterministic contracts for mutation-prone service boundaries."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

import app.auth.security as security
import app.core.database as database
import app.services.nats_messaging as nats_messaging
import app.workers.outbox as outbox
from app.core.nats_broker import NatsTaskBroker
from app.services import notification_queue as queue
from app.services.notification_service import NotificationService
from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


def _schedule_item(
    item_id: int,
    *,
    room: str,
    teacher: str,
) -> ScheduleItemInternal:
    return ScheduleItemInternal(
        id=item_id,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
        room=room,
        teacher=teacher,
    )


@pytest.mark.asyncio
async def test_news_enqueue_failure_report_keeps_complete_metadata() -> None:
    service = NotificationService(db=AsyncMock())
    news_id = uuid.uuid4()
    failure = RuntimeError("queue full")
    background = MagicMock(spec=BackgroundTasks)
    background.add_task.side_effect = failure

    with patch(
        "app.services.notification_service.notification_queue.report_enqueue_failure",
        new=AsyncMock(),
    ) as report:
        await service.dispatch_news_created(news_id, "en", background)

    report.assert_awaited_once_with(
        notification_type="news",
        record_id=news_id,
        error=failure,
        source="NotificationService.dispatch_news_created",
    )


@pytest.mark.asyncio
async def test_dead_letter_cleanup_normalizes_naive_timestamp_before_cutoff() -> None:
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)

    await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=datetime(2026, 8, 17),
    )

    statement = db.execute.await_args.args[0]
    cutoff = next(
        value
        for name, value in statement.compile().params.items()
        if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 8, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_dead_letter_cleanup_normalizes_aware_non_utc_timestamp_before_cutoff() -> (
    None
):
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)

    await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=datetime(2026, 8, 17, 3, tzinfo=timezone(timedelta(hours=3))),
    )

    statement = db.execute.await_args.args[0]
    cutoff = next(
        value
        for name, value in statement.compile().params.items()
        if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 8, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_dead_letter_cleanup_rejects_negative_retention_with_exact_message() -> (
    None
):
    with pytest.raises(ValueError) as exc_info:
        await queue.cleanup_dead_lettered_jobs(-1, db=AsyncMock())

    assert str(exc_info.value) == "retention_days must be non-negative"


@pytest.mark.asyncio
async def test_nats_connect_preserves_unlimited_reconnect_policy() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_nc = MagicMock()
    mock_nc.jetstream.return_value = mock_js

    with patch(
        "app.core.nats_broker.nats.connect",
        new=AsyncMock(return_value=mock_nc),
    ) as connect:
        await broker.connect()

    kwargs = connect.await_args.kwargs
    assert kwargs["max_reconnect_attempts"] == -1
    assert kwargs["connect_timeout"] == 2


def test_get_nats_service_uses_configured_server_and_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nats_messaging, "_nats_service", None)
    settings = SimpleNamespace(
        nats_url="nats://configured.example:4222",
        nats_auth_token="configured-token",
    )
    instance = MagicMock()

    with (
        patch("app.core.config.settings", settings),
        patch.object(
            nats_messaging, "NatsService", return_value=instance
        ) as constructor,
    ):
        assert nats_messaging.get_nats_service() is instance

    constructor.assert_called_once_with(
        servers="nats://configured.example:4222",
        auth_token="configured-token",
    )


def test_unsupported_password_hash_warning_keeps_security_contract() -> None:
    with patch.object(security._logger, "warning") as warning:
        security._warn_unsupported_password_hash()

    warning.assert_called_once_with(
        "unsupported_password_hash_rejected: only argon2id hashes are accepted; "
        "the user must reset their password",
    )


def test_database_invalidation_keeps_structured_log_message() -> None:
    with (
        patch.object(database._pool_metrics, "record_invalidation") as record,
        patch.object(database.pool_health_logger, "warning") as warning,
    ):
        database._on_invalidate(None, None, RuntimeError("database reset"))

    record.assert_called_once_with()
    warning.assert_called_once_with(
        "Connection invalidated",
        active_connections=database._pool_metrics.active_connections,
        exception_type="RuntimeError",
    )


@pytest.mark.asyncio
async def test_outbox_main_passes_runtime_heartbeat_path_to_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("app.core.database.init_database", lambda: None)

    async def wait_db(*_args: object, **_kwargs: object) -> None:
        return None

    async def register_listeners() -> None:
        return None

    async def stop_on_signal(stop_event: asyncio.Event) -> None:
        stop_event.set()

    monkeypatch.setattr("app.core.database.wait_db", wait_db)
    monkeypatch.setattr("app.core.events.register_event_listeners", register_listeners)
    monkeypatch.setattr(
        "app.services.event_handlers.configure_event_handlers", lambda: None
    )
    monkeypatch.setattr(outbox, "_wait_for_signals", stop_on_signal)
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("OUTBOX_WORKER_RUNTIME_DIR", str(runtime_dir))

    worker = MagicMock()
    worker.run_forever = AsyncMock()
    worker.stop = AsyncMock()
    settings = SimpleNamespace(
        outbox_poll_interval_seconds=0.25,
        outbox_batch_size=4,
        outbox_max_retries=2,
    )

    with (
        patch("app.core.config.settings", settings),
        patch.object(outbox, "OutboxWorker", return_value=worker) as constructor,
        patch("app.core.nats_broker.broker.connect", new_callable=AsyncMock),
        patch("app.core.nats_broker.broker.close", new_callable=AsyncMock),
    ):
        await outbox.main()

    constructor.assert_called_once_with(
        poll_interval=0.25,
        batch_size=4,
        max_retries=2,
        heartbeat_path=runtime_dir / "worker.heartbeat",
    )
    worker.run_forever.assert_awaited_once()
    worker.stop.assert_awaited_once()


def test_uuid_rust_conversion_uses_stable_four_byte_prefix() -> None:
    service = ScheduleOptimizerService()
    item_id = uuid.UUID("12345678-1234-5678-90ab-cdef12345678")
    item = ScheduleItemInternal(
        id=item_id,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    rust_item = service._to_rust_item(item)

    expected_id = int.from_bytes(item_id.bytes[:4], "big") & 0x7FFFFFFF
    assert rust_item.id == expected_id


@pytest.mark.asyncio
async def test_batch_conflict_stub_restores_both_domain_metadata() -> None:
    service = ScheduleOptimizerService()
    first = _schedule_item(101, room="101A", teacher="Dr. Smith")
    second = _schedule_item(202, room="202B", teacher="Prof. Jones")

    def return_first_pair(rust_items):
        return [(rust_items[0], rust_items[1])]

    with patch(
        "rust_ext.batch_detect_conflicts",
        side_effect=return_first_pair,
    ):
        conflicts = await service.batch_detect_conflicts([first, second])

    assert len(conflicts) == 1
    returned = {item.id: item for pair in conflicts for item in pair}
    assert returned[101].room == "101A"
    assert returned[101].teacher == "Dr. Smith"
    assert returned[202].room == "202B"
    assert returned[202].teacher == "Prof. Jones"
