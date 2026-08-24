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


async def test_connect_registers_both_streams_and_lifecycle_callbacks() -> None:
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)

    with patch("nats.connect", new_callable=AsyncMock, return_value=mock_nc) as connect:
        await broker.connect()

        kwargs = connect.call_args.kwargs
        assert kwargs["connect_timeout"] == 2
        await kwargs["reconnected_cb"]()
        await kwargs["disconnected_cb"]()

    assert mock_js.add_stream.await_count == 5
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


@pytest.mark.asyncio
async def test_connect_preserves_cleanup_failure_detail_when_provisioning_fails() -> (
    None
):
    broker = NatsTaskBroker()
    mock_js = MagicMock()
    mock_js.add_stream = AsyncMock(side_effect=RuntimeError("provisioning failed"))
    mock_nc = MagicMock()
    mock_nc.jetstream.return_value = mock_js

    with (
        patch("app.core.nats_broker.nats.connect", new=AsyncMock(return_value=mock_nc)),
        patch.object(
            broker, "close", new=AsyncMock(side_effect=RuntimeError("cleanup failed"))
        ) as close,
        patch.object(nats_broker_module._logger, "warning") as warning,
        pytest.raises(RuntimeError, match="provisioning failed"),
    ):
        await broker.connect()

    close.assert_awaited_once()
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

    mock_nc.close.assert_not_awaited()
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
