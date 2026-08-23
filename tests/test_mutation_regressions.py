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
from app.services.webpush import build_payload


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
async def test_dead_letter_cleanup_attaches_utc_to_naive_clock() -> None:
    seen_timezones: list[object] = []

    class TrackingNaiveDateTime(datetime):
        def replace(self, **kwargs: object) -> datetime:  # type: ignore[override]
            seen_timezones.append(kwargs.get("tzinfo"))
            return datetime(2026, 8, 17, tzinfo=UTC)

    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)

    await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=TrackingNaiveDateTime(2026, 8, 17),
    )

    assert seen_timezones == [UTC]


@pytest.mark.asyncio
async def test_dead_letter_cleanup_uses_utc_clock_when_now_is_omitted() -> None:
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)
    datetime_type = MagicMock(wraps=datetime)
    datetime_type.now = MagicMock(
        side_effect=lambda tz=None: datetime(2026, 8, 17, tzinfo=tz)
    )

    with patch.object(queue, "datetime", datetime_type):
        deleted = await queue.cleanup_dead_lettered_jobs(db=db)

    datetime_type.now.assert_called_once_with(UTC)
    assert deleted == 0


@pytest.mark.asyncio
async def test_dead_letter_cleanup_normalizes_aware_non_utc_timestamp_before_cutoff() -> (
    None
):
    seen_timezones: list[object] = []

    class TrackingDateTime(datetime):
        def astimezone(self, tz=None):  # type: ignore[override]
            seen_timezones.append(tz)
            return datetime(2026, 8, 17, 0, tzinfo=UTC)

    db = AsyncMock()
    db.execute.return_value = object()

    deleted = await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=TrackingDateTime(2026, 8, 17, 3, tzinfo=timezone(timedelta(hours=3))),
    )

    statement = db.execute.await_args.args[0]
    cutoff = next(
        value
        for name, value in statement.compile().params.items()
        if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 8, 10, tzinfo=UTC)
    assert seen_timezones == [UTC]
    assert deleted == 0


@pytest.mark.asyncio
async def test_dead_letter_cleanup_reapplies_explicit_utc_to_cutoff() -> None:
    seen_timezones: list[object] = []

    class TrackingDateTime(datetime):
        def astimezone(self, tz=None):  # type: ignore[override]
            seen_timezones.append(tz)
            return self

    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)

    await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=TrackingDateTime(2026, 8, 17, 3, tzinfo=timezone(timedelta(hours=3))),
    )

    assert seen_timezones == [UTC, UTC]


@pytest.mark.asyncio
async def test_dead_letter_cleanup_converts_non_utc_offset_before_cutoff() -> None:
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=0)

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
async def test_dead_letter_cleanup_forwards_retention_to_owned_session() -> None:
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db)
    session_context.__aexit__ = AsyncMock(return_value=False)

    with patch.object(queue, "async_session", return_value=session_context):
        await queue.cleanup_dead_lettered_jobs(
            7,
            now=datetime(2026, 8, 17, tzinfo=UTC),
        )

    statement = db.execute.await_args.args[0]
    cutoff = next(
        value
        for name, value in statement.compile().params.items()
        if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 8, 10, tzinfo=UTC)
    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_dead_letter_cleanup_treats_none_rowcount_as_zero() -> None:
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=None)

    deleted = await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert deleted == 0


@pytest.mark.asyncio
async def test_dead_letter_cleanup_rejects_negative_retention_with_exact_message() -> (
    None
):
    with pytest.raises(ValueError) as exc_info:
        await queue.cleanup_dead_lettered_jobs(-1, db=AsyncMock())

    assert str(exc_info.value) == "retention_days must be non-negative"


@pytest.mark.asyncio
async def test_outbox_shutdown_awaits_every_auxiliary_task() -> None:
    worker = outbox.OutboxWorker()
    worker.heartbeat_path = Path("heartbeat")

    async def stop_on_first_batch() -> int:
        raise asyncio.CancelledError

    worker.process_batch = stop_on_first_batch  # type: ignore[method-assign]
    listen_task = MagicMock(name="listen_task")
    heartbeat_task = MagicMock(name="heartbeat_task")
    gather = AsyncMock()
    tasks = iter((listen_task, heartbeat_task))

    def fake_create_task(coro):
        coro.close()
        return next(tasks)

    with (
        patch.object(outbox.asyncio, "create_task", side_effect=fake_create_task),
        patch.object(outbox.asyncio, "gather", new=gather),
        pytest.raises(asyncio.CancelledError),
    ):
        await worker.run_forever()

    listen_task.cancel.assert_called_once_with()
    heartbeat_task.cancel.assert_called_once_with()
    gather.assert_awaited_once_with(
        listen_task,
        heartbeat_task,
        return_exceptions=True,
    )


def test_build_payload_ignores_non_numeric_optional_timestamp() -> None:
    payload = build_payload(
        "system.message",
        {"message": "hello", "timestamp": object()},
    )

    assert "timestamp" not in payload["options"]


def test_build_payload_omits_explicitly_empty_optional_timestamp() -> None:
    payload = build_payload("system.message", {"timestamp": None})

    assert "timestamp" not in payload["options"]


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


def test_database_invalidation_without_exception_uses_none_type_marker() -> None:
    with (
        patch.object(database._pool_metrics, "record_invalidation"),
        patch.object(database.pool_health_logger, "warning") as warning,
    ):
        database._on_invalidate(None, None, None)

    assert warning.call_args.kwargs["exception_type"] == "None"


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


def test_uuid_rust_conversion_honors_valid_override_and_rejects_invalid_one() -> None:
    service = ScheduleOptimizerService()
    item = ScheduleItemInternal(
        id=uuid.UUID("12345678-1234-5678-90ab-cdef12345678"),
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    assert service._to_rust_item(item, rust_id_override=123).id == 123
    assert service._to_rust_item(item, rust_id_override=None).id is None


def test_uuid_surrogate_allocator_moves_down_from_occupied_i32_max() -> None:
    service = ScheduleOptimizerService()
    occupied = _schedule_item(2_147_483_647, room="max", teacher="Boundary")
    uuid_item = ScheduleItemInternal(
        id=uuid.UUID("018f0000-0000-7000-8000-000000000001"),
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    def fake_to_rust_item(item: ScheduleItemInternal, **kwargs: object) -> object:
        return SimpleNamespace(id=kwargs.get("rust_id_override", item.id))

    with patch.object(service, "_to_rust_item", side_effect=fake_to_rust_item):
        rust_items, rust_id_map = service._to_rust_items_with_unique_ids(
            [occupied, uuid_item]
        )

    assert [item.id for item in rust_items] == [2_147_483_647, 2_147_483_646]
    assert rust_id_map == {2_147_483_647: occupied, 2_147_483_646: uuid_item}


@pytest.mark.timeout(5)
def test_uuid_surrogate_allocator_passes_item_to_native_converter() -> None:
    service = ScheduleOptimizerService()
    item = ScheduleItemInternal(
        id=uuid.UUID("018f0000-0000-7000-8000-000000000001"),
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )
    second_item = item.model_copy(
        update={
            "id": uuid.UUID("018f0000-0000-7000-8000-000000000002"),
            "room": "102B",
        }
    )

    integer_item = item.model_copy(update={"id": 42})
    calls: list[tuple[object, int | None]] = []

    def strict_to_rust_item(
        converted_item: object, *, rust_id_override: int | None = None
    ) -> object:
        calls.append((converted_item, rust_id_override))
        return SimpleNamespace(
            id=(
                rust_id_override
                if rust_id_override is not None
                else getattr(converted_item, "id", None)
            )
        )

    with patch.object(service, "_to_rust_item", side_effect=strict_to_rust_item):
        rust_items, _ = service._to_rust_items_with_unique_ids(
            [item, second_item, integer_item]
        )

    assert calls == [
        (item, 2_147_483_647),
        (second_item, 2_147_483_646),
        (integer_item, None),
    ]
    assert [rust_item.id for rust_item in rust_items] == [
        2_147_483_647,
        2_147_483_646,
        42,
    ]


@pytest.mark.asyncio
async def test_batch_conflicts_passes_b_item_to_native_reconstruction() -> None:
    service = ScheduleOptimizerService()
    first = _schedule_item(101, room="101A", teacher="Dr. Smith")
    second = _schedule_item(202, room="202B", teacher="Prof. Jones")

    def return_first_pair(rust_items):
        return [(rust_items[0], rust_items[1])]

    reconstructed: list[tuple[object, str | None, str | None]] = []

    def strict_from_rust_item(
        native_item: object,
        original_room: str | None,
        original_teacher: str | None,
    ) -> ScheduleItemInternal:
        reconstructed.append((native_item, original_room, original_teacher))
        return ScheduleItemInternal(
            id=getattr(native_item, "id", None),
            weekday="Monday",
            start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            parity="both",
        )

    with (
        patch("rust_ext.batch_detect_conflicts", side_effect=return_first_pair),
        patch.object(service, "_from_rust_item", side_effect=strict_from_rust_item),
    ):
        conflicts = await service.batch_detect_conflicts([first, second])

    assert len(conflicts) == 1
    assert [entry[0].id for entry in reconstructed] == [101, 202]
    assert reconstructed[0][1:] == ("101A", "Dr. Smith")
    assert reconstructed[1][1:] == ("202B", "Prof. Jones")


def test_imgproxy_base_url_removes_trailing_slashes() -> None:
    from app.utils.img import get_optimized_image_url

    settings = SimpleNamespace(
        imgproxy_key="0" * 64,
        imgproxy_salt="1" * 64,
        imgproxy_base_url="https://img.example.com///",
    )

    with patch("app.utils.img.settings", settings):
        result = get_optimized_image_url("https://cdn.example.com/photo.jpg")

    assert result is not None
    assert result.startswith("https://img.example.com/")
    assert not result.startswith("https://img.example.com//")


def test_imgproxy_base_url_preserves_non_slash_suffix() -> None:
    from app.utils.img import get_optimized_image_url

    settings = SimpleNamespace(
        imgproxy_key="0" * 64,
        imgproxy_salt="1" * 64,
        imgproxy_base_url="https://img.example.comX",
    )

    with patch("app.utils.img.settings", settings):
        result = get_optimized_image_url("https://cdn.example.com/photo.jpg")

    assert result is not None
    assert result.startswith("https://img.example.comX/")


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
