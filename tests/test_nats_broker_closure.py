"""Focused closure tests for the NATS broker quality hotspot."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import nats
import pytest

import app.core.nats_broker as nats_broker_module
from app.core.nats_broker import NatsTaskBroker, Task, _NatsTaskPayload, set_app


def _message(payload: dict) -> AsyncMock:
    message = AsyncMock()
    message.data = json.dumps(payload).encode()
    return message


def _payload(name: str, *, args: list | None = None) -> dict:
    return {
        "id": "task-id",
        "name": name,
        "args": args or [],
        "kwargs": {},
        "trace_context": {},
    }


async def test_connect_registers_streams_and_lifecycle_callbacks() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)

    legacy_connect = AsyncMock(return_value=mock_nc)
    with (
        patch("app.core.nats_broker.nats.connect", new=legacy_connect),
        patch("app.core.nats_broker.NATS", return_value=mock_nc) as client_factory,
    ):
        await broker.connect()

        kwargs = (
            legacy_connect.await_args.kwargs
            if legacy_connect.await_count
            else mock_nc.connect.call_args.kwargs
        )
        assert client_factory.call_count + legacy_connect.await_count == 1
        assert mock_nc.connect.await_count + legacy_connect.await_count == 1
        assert kwargs["connect_timeout"] == 2
        await kwargs["reconnected_cb"]()
        await kwargs["disconnected_cb"]()

    assert mock_js.add_stream.await_count == 6
    configs = [c.kwargs["config"] for c in mock_js.add_stream.await_args_list]
    assert configs[0].name == "TASK_QUEUE"
    assert configs[0].subjects == ["tasks.>"]
    assert configs[1].name == "FILES_PROCESS"
    assert configs[1].subjects == ["files.process"]
    assert configs[2].name == "CHAT_EVENTS"
    assert configs[2].subjects == ["chat.*"]
    assert configs[3].name == "NOTIFICATIONS_EVENTS"
    assert configs[3].subjects == ["notifications.*"]
    assert configs[4].name == "OUTBOX_EVENTS"
    assert configs[4].subjects == ["outbox.*"]
    assert configs[5].name == "CACHE_INVALIDATIONS"
    assert configs[5].subjects == ["cache.invalidate"]


async def test_concurrent_connects_share_one_initialization() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    started = asyncio.Event()
    release = asyncio.Event()

    async def add_stream(**kwargs: object) -> None:
        del kwargs
        started.set()
        await asyncio.wait_for(release.wait(), timeout=1)

    mock_js.add_stream.side_effect = add_stream
    legacy_connect = AsyncMock(return_value=mock_nc)
    first: asyncio.Task[None] | None = None
    second: asyncio.Task[None] | None = None
    try:
        with (
            patch("app.core.nats_broker.nats.connect", new=legacy_connect),
            patch("app.core.nats_broker.NATS", return_value=mock_nc) as client_factory,
        ):
            first = asyncio.create_task(broker.connect())
            await asyncio.wait_for(started.wait(), timeout=1)
            assert broker._js is None
            second = asyncio.create_task(broker.connect())
            await asyncio.sleep(0)
            assert not second.done()
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
            assert client_factory.call_count + legacy_connect.await_count == 1
            assert mock_nc.connect.await_count + legacy_connect.await_count == 1
            assert mock_js.add_stream.await_count == 6
    finally:
        release.set()
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=1
            )


async def test_connect_cancellation_closes_partial_client() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    started = asyncio.Event()
    wait_forever = asyncio.Event()

    async def connect(*args: object, **kwargs: object) -> None:
        del args, kwargs
        started.set()
        await wait_forever.wait()

    async def legacy_connect_impl(*args: object, **kwargs: object) -> AsyncMock:
        await mock_nc.connect(*args, **kwargs)
        return mock_nc

    mock_nc.connect.side_effect = connect
    legacy_connect = AsyncMock(side_effect=legacy_connect_impl)
    task: asyncio.Task[None] | None = None
    with (
        patch("app.core.nats_broker.nats.connect", new=legacy_connect),
        patch("app.core.nats_broker.NATS", return_value=mock_nc),
    ):
        try:
            task = asyncio.create_task(broker.connect())
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
        finally:
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                await asyncio.wait_for(
                    asyncio.gather(task, return_exceptions=True), timeout=1
                )

    assert mock_nc.close.await_count == 1
    assert broker._nc is None
    assert broker._js is None


async def test_connect_has_a_total_deadline_and_cleans_up() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    wait_forever = asyncio.Event()

    async def connect(*args: object, **kwargs: object) -> None:
        del args, kwargs
        await wait_forever.wait()

    async def legacy_connect_impl(*args: object, **kwargs: object) -> AsyncMock:
        await mock_nc.connect(*args, **kwargs)
        return mock_nc

    mock_nc.connect.side_effect = connect
    legacy_connect = AsyncMock(side_effect=legacy_connect_impl)

    deadline_guard = asyncio.Event()

    async def expire_outer_guard() -> None:
        await asyncio.sleep(0.4)
        deadline_guard.set()

    outer_guard = asyncio.create_task(expire_outer_guard())
    try:
        with (
            patch("app.core.nats_broker.nats.connect", new=legacy_connect),
            patch("app.core.nats_broker.NATS", return_value=mock_nc),
            patch("app.core.nats_broker._CONNECT_TIMEOUT_S", 0.01, create=True),
            pytest.raises(TimeoutError),
        ):
            await asyncio.wait_for(broker.connect(), timeout=0.5)
        assert not deadline_guard.is_set()
    finally:
        if not outer_guard.done():
            outer_guard.cancel()
        await asyncio.wait_for(
            asyncio.gather(outer_guard, return_exceptions=True), timeout=1
        )

    assert legacy_connect.await_count + mock_nc.connect.await_count >= 1
    assert mock_nc.close.await_count == 1
    assert broker._nc is None
    assert broker._js is None


@pytest.mark.asyncio
async def test_connect_preserves_cleanup_failure_detail_when_provisioning_fails() -> (
    None
):
    broker = NatsTaskBroker()
    mock_js = MagicMock()
    mock_js.add_stream = AsyncMock(side_effect=RuntimeError("provisioning failed"))
    mock_nc = MagicMock()
    mock_nc.connect = AsyncMock()
    mock_nc.jetstream.return_value = mock_js

    legacy_connect = AsyncMock(return_value=mock_nc)
    close_legacy = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    close_unlocked = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    with (
        patch("app.core.nats_broker.nats.connect", new=legacy_connect),
        patch("app.core.nats_broker.NATS", return_value=mock_nc) as client_factory,
        patch.object(broker, "close", new=close_legacy),
        patch.object(broker, "_close_unlocked", new=close_unlocked, create=True),
        patch.object(nats_broker_module._logger, "warning") as warning,
        pytest.raises(RuntimeError, match="provisioning failed"),
    ):
        await broker.connect()

    assert client_factory.call_count + legacy_connect.await_count == 1
    assert close_legacy.await_count + close_unlocked.await_count == 1
    assert warning.call_args.args[0] == "Failed to close partial NATS connection: %s"
    assert isinstance(warning.call_args.args[1], RuntimeError)
    assert str(warning.call_args.args[1]) == "cleanup failed"


async def test_close_clears_disconnected_client_without_close_call() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = False
    broker._nc = mock_nc
    broker._js = AsyncMock()

    await broker.close()

    mock_nc.close.assert_awaited_once()
    assert broker._nc is None
    assert broker._js is None


async def test_close_swallows_network_error_and_clears_state() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    mock_nc.close.side_effect = OSError("connection already gone")
    broker._nc = mock_nc
    broker._js = AsyncMock()

    await broker.close()

    assert broker._nc is None
    assert broker._js is None


async def test_task_kick_enqueues_registered_task() -> None:
    broker = NatsTaskBroker()

    @broker.task(name="closure.kick")
    async def task_handler(value: int) -> None:
        del value

    with patch.object(broker, "enqueue", new_callable=AsyncMock) as enqueue:
        await task_handler.kick(42)

    enqueue.assert_awaited_once_with("closure.kick", 42)


async def test_task_protocol_stubs_are_executable_type_contracts() -> None:
    assert await Task.__call__(object()) is None
    assert await Task.kick(object()) is None


def test_task_payload_rejects_blank_names() -> None:
    with pytest.raises(ValueError, match="task name must not be empty"):
        _NatsTaskPayload(id="task-id", name=" ")


@pytest.mark.parametrize("method_name", ["publish", "enqueue"])
async def test_jetstream_methods_raise_when_connect_does_not_provide_js(
    method_name: str,
) -> None:
    broker = NatsTaskBroker()

    with patch.object(broker, "connect", new_callable=AsyncMock) as connect:
        method = getattr(broker, method_name)
        with pytest.raises(RuntimeError, match="JetStream not available"):
            if method_name == "publish":
                await method("events.test", {"value": 1})
            else:
                await method("closure.task")

    connect.assert_awaited_once()


@pytest.mark.parametrize("method_name", ["publish", "enqueue"])
async def test_jetstream_methods_skip_publish_for_falsy_context(
    method_name: str,
) -> None:
    broker = NatsTaskBroker()
    mock_js = MagicMock()
    mock_js.__bool__.return_value = False
    broker._js = mock_js

    method = getattr(broker, method_name)
    if method_name == "publish":
        result = await method("events.test", {"value": 1})
    else:
        result = await method("closure.task")

    assert result is None or isinstance(result, str)
    mock_js.publish.assert_not_called()


async def test_publish_core_swallows_network_error() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    mock_nc.publish.side_effect = ConnectionError("NATS unavailable")
    broker._nc = mock_nc

    await broker.publish_core("chat.direct", {"value": 1})

    mock_nc.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_cancellation_while_waiting_for_lock_preserves_lock_owner() -> (
    None
):
    broker = NatsTaskBroker()
    await broker._connect_lock.acquire()
    task: asyncio.Task[None] | None = None

    try:
        with patch("app.core.nats_broker.NATS") as client_factory:
            task = asyncio.create_task(broker.connect())
            await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
            client_factory.assert_not_called()

        assert broker._nc is None
        assert broker._js is None
        assert broker._connect_lock.locked()
    finally:
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), timeout=1
            )
        broker._connect_lock.release()


@pytest.mark.asyncio
async def test_connect_timeout_while_waiting_for_lock_preserves_lock_owner() -> None:
    broker = NatsTaskBroker()
    await broker._connect_lock.acquire()

    try:
        with (
            patch("app.core.nats_broker._CONNECT_TIMEOUT_S", 0.01),
            patch("app.core.nats_broker.NATS") as client_factory,
            pytest.raises(TimeoutError),
        ):
            await broker.connect()

        client_factory.assert_not_called()
        assert broker._nc is None
        assert broker._js is None
        assert broker._connect_lock.locked()
    finally:
        broker._connect_lock.release()


@pytest.mark.asyncio
async def test_run_worker_propagates_cancellation_during_initial_connect() -> None:
    broker = NatsTaskBroker()
    connect_started = asyncio.Event()
    never_ready = asyncio.Event()

    async def wait_for_connection() -> None:
        connect_started.set()
        await never_ready.wait()

    broker._js = None
    task: asyncio.Task[None] | None = None
    with (
        patch.object(broker, "connect", side_effect=wait_for_connection),
        patch("app.core.nats_broker.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        try:
            task = asyncio.create_task(broker.run_worker())
            await asyncio.wait_for(connect_started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
        finally:
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                await asyncio.wait_for(
                    asyncio.gather(task, return_exceptions=True), timeout=1
                )

    sleep.assert_not_awaited()


async def test_run_worker_retries_initial_nats_outage() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    mock_sub.fetch.side_effect = asyncio.CancelledError()
    attempts = 0

    async def connect() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise nats.errors.NoServersError()
        broker._js = mock_js

    with (
        patch.object(broker, "connect", side_effect=connect),
        patch("app.core.nats_broker.asyncio.sleep", new=AsyncMock()),
        pytest.raises(asyncio.CancelledError),
    ):
        await broker.run_worker()

    assert attempts == 2
    mock_js.pull_subscribe.assert_awaited_once_with(
        subject="tasks.>", durable="python-worker"
    )


async def test_run_worker_connects_before_subscribing() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    mock_sub.fetch.side_effect = asyncio.CancelledError()

    async def connect() -> None:
        broker._js = mock_js

    with patch.object(broker, "connect", side_effect=connect) as connect_mock:
        with pytest.raises(asyncio.CancelledError):
            await broker.run_worker()

    connect_mock.assert_awaited_once()
    mock_js.pull_subscribe.assert_awaited_once()


async def test_run_worker_executes_sync_handler_without_dishka() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    message = _message(_payload("closure.sync", args=[7]))
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js
    received: list[int] = []

    @broker.task(name="closure.sync")
    def sync_handler(value: int) -> None:
        received.append(value)

    set_app(None)
    with pytest.raises(asyncio.CancelledError):
        await broker.run_worker()

    assert received == [7]
    message.ack.assert_awaited_once()


async def test_run_worker_executes_sync_handler_inside_dishka_container() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    message = _message(_payload("closure.sync.di", args=[11]))
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js
    received: list[int] = []

    @broker.task(name="closure.sync.di")
    def sync_handler(value: int) -> None:
        received.append(value)

    request_container = AsyncMock()
    request_container.__aenter__.return_value = object()
    app = SimpleNamespace(
        state=SimpleNamespace(
            dishka_container=MagicMock(return_value=request_container)
        )
    )
    set_app(app)
    try:
        with patch(
            "dishka.integrations.base.wrap_injection", lambda func, **kwargs: func
        ):
            with pytest.raises(asyncio.CancelledError):
                await broker.run_worker()
    finally:
        set_app(None)

    assert received == [11]
    message.ack.assert_awaited_once()


async def test_run_worker_naks_timed_out_task() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    message = _message(_payload("closure.timeout"))
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js

    @broker.task(name="closure.timeout")
    async def timeout_handler() -> None:
        await asyncio.sleep(1)

    with (
        patch.object(nats_broker_module, "_DEFAULT_TASK_TIMEOUT_S", 0),
        pytest.raises(asyncio.CancelledError),
    ):
        await broker.run_worker()

    message.nak.assert_awaited_once()
    message.ack.assert_not_awaited()


async def test_run_worker_naks_handler_failure() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    message = _message(_payload("closure.failure"))
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js

    @broker.task(name="closure.failure")
    async def failing_handler() -> None:
        raise RuntimeError("handler failed")

    with pytest.raises(asyncio.CancelledError):
        await broker.run_worker()

    message.nak.assert_awaited_once()
    message.ack.assert_not_awaited()


async def test_run_worker_continues_after_fetch_timeout() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    mock_sub.fetch.side_effect = [nats.errors.TimeoutError(), asyncio.CancelledError()]
    broker._js = mock_js

    with pytest.raises(asyncio.CancelledError):
        await broker.run_worker()

    assert mock_sub.fetch.await_count == 2


async def test_run_worker_sleeps_after_unexpected_fetch_error() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    mock_sub.fetch.side_effect = [
        RuntimeError("fetch failed"),
        asyncio.CancelledError(),
    ]
    broker._js = mock_js

    with patch.object(
        nats_broker_module.asyncio, "sleep", new_callable=AsyncMock
    ) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await broker.run_worker()

    sleep.assert_awaited_once_with(1)


def test_jetstream_property_returns_current_context() -> None:
    broker = NatsTaskBroker()
    context = object()
    broker._js = context  # type: ignore[assignment]

    assert broker.js is context


# --- Bounded redelivery / dead-letter queue -----------------------------------


def _task(name: str = "demo") -> _NatsTaskPayload:
    return _NatsTaskPayload(
        id="task-1", name=name, args=[1, "two"], kwargs={"flag": True}
    )


def _delivered(count: int) -> AsyncMock:
    message = AsyncMock()
    message.metadata = SimpleNamespace(num_delivered=count)
    return message


def test_num_delivered_defaults_to_one_without_jetstream_metadata() -> None:
    assert NatsTaskBroker._num_delivered(_delivered(4)) == 4
    assert NatsTaskBroker._num_delivered(object()) == 1
    assert NatsTaskBroker._num_delivered(SimpleNamespace(metadata=None)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("delivered", "delay"), [(1, 5.0), (2, 10.0), (4, 40.0)])
async def test_failed_task_is_nacked_with_exponential_backoff(
    delivered: int, delay: float
) -> None:
    broker = NatsTaskBroker()
    message = _delivered(delivered)
    broker._dead_letter = AsyncMock()  # type: ignore[method-assign]

    with patch.object(nats_broker_module, "_MAX_DELIVERIES", 10):
        await broker._retry_or_dead_letter(message, _task(), "boom")

    message.nak.assert_awaited_once_with(delay=delay)
    message.term.assert_not_awaited()
    broker._dead_letter.assert_not_awaited()


@pytest.mark.asyncio
async def test_backoff_is_capped() -> None:
    broker = NatsTaskBroker()
    message = _delivered(30)
    with patch.object(nats_broker_module, "_MAX_DELIVERIES", 100):
        await broker._retry_or_dead_letter(message, _task(), "boom")
    message.nak.assert_awaited_once_with(delay=nats_broker_module._RETRY_MAX_DELAY_S)


@pytest.mark.asyncio
async def test_exhausted_task_is_parked_in_dlq_and_terminated() -> None:
    broker = NatsTaskBroker()
    message = _delivered(nats_broker_module._MAX_DELIVERIES)
    broker._dead_letter = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await broker._retry_or_dead_letter(message, _task(), "boom")

    broker._dead_letter.assert_awaited_once()
    message.term.assert_awaited_once()
    message.nak.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_is_kept_alive_when_dlq_persistence_fails() -> None:
    broker = NatsTaskBroker()
    message = _delivered(nats_broker_module._MAX_DELIVERIES)
    broker._dead_letter = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await broker._retry_or_dead_letter(message, _task(), "boom")

    message.term.assert_not_awaited()
    message.nak.assert_awaited_once()


@pytest.mark.asyncio
async def test_dead_letter_persists_task_and_commits() -> None:
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    queue = MagicMock(add_failed_job=AsyncMock())

    with (
        patch("app.core.database.async_session", return_value=context),
        patch("app.workers.dead_letter_queue.DeadLetterQueue", return_value=queue),
    ):
        stored = await NatsTaskBroker()._dead_letter(_task(), "x" * 5000, 5)

    assert stored is True
    queue.add_failed_job.assert_awaited_once()
    call = queue.add_failed_job.await_args.kwargs
    assert call["job_type"] == "demo"
    assert call["payload"] == {"args": [1, "two"], "kwargs": {"flag": True}}
    assert len(call["error_message"]) == 2000
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dead_letter_reports_persistence_failure() -> None:
    from sqlalchemy.exc import OperationalError

    with patch(
        "app.core.database.async_session",
        side_effect=OperationalError("stmt", {}, Exception("db down")),
    ):
        assert await NatsTaskBroker()._dead_letter(_task(), "boom", 5) is False


@pytest.mark.asyncio
async def test_replay_dead_letter_reenqueues_original_arguments() -> None:
    broker = NatsTaskBroker()
    broker.enqueue = AsyncMock()  # type: ignore[method-assign]

    await broker.replay_dead_letter("demo", {"args": [1], "kwargs": {"a": 2}})
    await broker.replay_dead_letter("bare", {})

    assert broker.enqueue.await_args_list[0].args == ("demo", 1)
    assert broker.enqueue.await_args_list[0].kwargs == {"a": 2}
    assert broker.enqueue.await_args_list[1].args == ("bare",)


async def test_run_worker_dead_letters_task_after_max_deliveries() -> None:
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    message = _message(_payload("closure.poison"))
    message.metadata = SimpleNamespace(num_delivered=nats_broker_module._MAX_DELIVERIES)
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js
    broker._dead_letter = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @broker.task(name="closure.poison")
    async def poison_handler() -> None:
        raise RuntimeError("always fails")

    with pytest.raises(asyncio.CancelledError):
        await broker.run_worker()

    broker._dead_letter.assert_awaited_once()
    message.term.assert_awaited_once()
    message.nak.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("persistence_succeeds", [True, False])
async def test_run_worker_unknown_handler_at_limit_persists_before_term_or_naks(
    persistence_succeeds: bool,
) -> None:
    """Persist real DLQ rows before termination; retain delivery on commit failure."""
    from sqlalchemy.exc import OperationalError

    from app.models.dead_letter import DeadLetterJob

    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub
    task_name = "closure.unregistered"
    message = _message(_payload(task_name, args=[7]))
    deliveries = nats_broker_module._MAX_DELIVERIES
    message.metadata = SimpleNamespace(num_delivered=deliveries)
    mock_sub.fetch.side_effect = [[message], asyncio.CancelledError()]
    broker._js = mock_js

    events: list[str] = []
    persisted_jobs: list[DeadLetterJob] = []
    session = AsyncMock()
    context = MagicMock()

    async def enter_session() -> AsyncMock:
        events.append("dlq.session_open")
        return session

    async def exit_session(*_args: object) -> bool:
        events.append("dlq.session_close")
        return False

    async def find_existing_job(*_args: object, **_kwargs: object) -> SimpleNamespace:
        events.append("dlq.query")
        return SimpleNamespace(scalar_one_or_none=MagicMock(return_value=None))

    def add_job(job: DeadLetterJob) -> None:
        events.append("dlq.add")
        persisted_jobs.append(job)

    async def flush() -> None:
        events.append("dlq.flush")

    async def commit() -> None:
        if persistence_succeeds:
            events.append("dlq.commit")
            return
        events.append("dlq.commit_failed")
        raise OperationalError("insert", {}, OSError("database unavailable"))

    async def terminate() -> None:
        events.append("message.term")

    async def negative_ack(*, delay: float) -> None:
        del delay
        events.append("message.nak")

    context.__aenter__ = AsyncMock(side_effect=enter_session)
    context.__aexit__ = AsyncMock(side_effect=exit_session)
    session.execute.side_effect = find_existing_job
    session.add = MagicMock(side_effect=add_job)
    session.flush.side_effect = flush
    session.commit.side_effect = commit
    message.term.side_effect = terminate
    message.nak.side_effect = negative_ack

    with (
        patch("app.core.database.async_session", return_value=context),
        patch.object(nats_broker_module, "_RETRY_BASE_DELAY_S", 0.125),
        pytest.raises(asyncio.CancelledError),
    ):
        await broker.run_worker()

    assert len(persisted_jobs) == 1
    row = persisted_jobs[0]
    assert isinstance(row, DeadLetterJob)
    assert row.job_type == task_name
    assert json.loads(row.payload) == {"args": [7], "kwargs": {}}
    assert row.error_message == f"no handler registered for task: {task_name}"
    assert len(row.job_hash) == 64
    assert row.next_retry_at is not None
    session.execute.assert_awaited_once()
    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
    message.ack.assert_not_awaited()

    if persistence_succeeds:
        assert events == [
            "dlq.session_open",
            "dlq.query",
            "dlq.add",
            "dlq.flush",
            "dlq.commit",
            "dlq.session_close",
            "message.term",
        ]
        message.term.assert_awaited_once()
        message.nak.assert_not_awaited()
    else:
        assert events == [
            "dlq.session_open",
            "dlq.query",
            "dlq.add",
            "dlq.flush",
            "dlq.commit_failed",
            "dlq.session_close",
            "message.nak",
        ]
        message.term.assert_not_awaited()
        expected_delay = min(
            0.125 * 2 ** (deliveries - 1), nats_broker_module._RETRY_MAX_DELAY_S
        )
        message.nak.assert_awaited_once_with(delay=expected_delay)


@pytest.mark.parametrize(
    "error_kind",
    ["invalid_url", "authorization", "invalid_credentials", "bad_subject"],
)
async def test_run_worker_propagates_permanent_connect_errors_without_retry(
    error_kind: str,
) -> None:
    """Only transient broker outages should enter the reconnect backoff."""
    from nats.aio.client import Client
    from nats.errors import (
        AuthorizationError,
        BadSubjectError,
        Error,
        InvalidUserCredentialsError,
    )

    if error_kind == "invalid_url":
        with pytest.raises(Error) as parsed_error:
            Client._parse_server_uri("nats://example.invalid:not-a-port")
        assert type(parsed_error.value) is Error
        error = parsed_error.value
    else:
        error_type = {
            "authorization": AuthorizationError,
            "invalid_credentials": InvalidUserCredentialsError,
            "bad_subject": BadSubjectError,
        }[error_kind]
        error = error_type()

    broker = NatsTaskBroker()
    connect = AsyncMock(side_effect=error)
    retry_sleep = AsyncMock(
        side_effect=AssertionError("permanent NATS error entered retry backoff")
    )

    with (
        patch.object(broker, "connect", new=connect),
        patch("app.core.nats_broker.asyncio.sleep", new=retry_sleep),
        pytest.raises(type(error)) as raised_error,
    ):
        await broker.run_worker()

    assert raised_error.value is error
    connect.assert_awaited_once_with()
    retry_sleep.assert_not_awaited()
