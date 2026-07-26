import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.nats_broker import NatsTaskBroker, set_app


@pytest.mark.anyio
async def test_nats_broker_connection_success():
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)

    with patch("nats.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_nc
        await broker.connect()

        # Should configure connect params
        mock_connect.assert_called_once()
        assert broker._nc is mock_nc
        assert broker._js is mock_js
        assert broker.is_connected is True

        # Idempotence: calling connect again should be a no-op
        await broker.connect()
        mock_connect.assert_called_once()


@pytest.mark.anyio
async def test_nats_broker_connection_failure():
    broker = NatsTaskBroker()

    with patch("nats.connect", side_effect=Exception("NATS connect error")):
        with pytest.raises(Exception, match="NATS connect error"):
            await broker.connect()

        assert broker._nc is None
        assert broker._js is None
        assert broker.is_connected is False


@pytest.mark.anyio
async def test_nats_broker_close():
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    broker._nc = mock_nc
    broker._js = AsyncMock()

    await broker.close()
    mock_nc.close.assert_called_once()
    assert broker._nc is None
    assert broker._js is None


@pytest.mark.anyio
async def test_nats_broker_task_decorator():
    broker = NatsTaskBroker()

    @broker.task(name="test.my_task")
    async def dummy_task(x, y=1):
        return x + y

    # Test decorator registration
    assert "test.my_task" in broker._tasks
    assert broker._tasks["test.my_task"] is dummy_task.__wrapped__

    # Direct invocation runs function synchronously/normally
    import inspect

    assert inspect.iscoroutinefunction(dummy_task)
    result = await dummy_task(5, y=10)
    assert result == 15


@pytest.mark.anyio
async def test_nats_broker_enqueue_and_publish():
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js

    # Test publish
    payload = {"event": "test"}
    await broker.publish("events.test", payload)
    mock_js.publish.assert_called_once()
    args, _ = mock_js.publish.call_args
    assert args[0] == "events.test"
    assert json.loads(args[1].decode()) == payload

    # Test enqueue
    mock_js.publish.reset_mock()
    task_id = await broker.enqueue("test.my_task", 5, y=10)
    assert task_id is not None
    mock_js.publish.assert_called_once()
    args, _ = mock_js.publish.call_args
    assert args[0] == "tasks.test.my_task"
    parsed_payload = json.loads(args[1].decode())
    assert parsed_payload["id"] == task_id
    assert parsed_payload["name"] == "test.my_task"
    assert parsed_payload["args"] == [5]
    assert parsed_payload["kwargs"] == {"y": 10}


@pytest.mark.anyio
async def test_nats_broker_publish_core():
    broker = NatsTaskBroker()

    # If not connected, publish_core should return early and not crash or connect
    with patch.object(broker, "connect", AsyncMock()) as mock_connect:
        await broker.publish_core("chat.message", {"msg": "hello"})
        mock_connect.assert_not_called()

    # If connected, call publish on client
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    broker._nc = mock_nc

    await broker.publish_core("chat.message", {"msg": "hello"})
    mock_nc.publish.assert_called_once()
    args, _ = mock_nc.publish.call_args
    assert args[0] == "chat.message"
    assert b"hello" in args[1]

    # Test nats.errors.Error (e.g., ConnectionClosedError) is caught gracefully
    import nats.errors

    mock_nc.publish.side_effect = nats.errors.ConnectionClosedError()
    await broker.publish_core("chat.message", {"msg": "hello"})  # Should not raise


@pytest.mark.anyio
async def test_nats_broker_run_worker():
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js

    # Mock task to run
    task_called_with = None

    @broker.task(name="test.run_worker_task")
    async def my_worker_task(val):
        nonlocal task_called_with
        task_called_with = val

    # Setup subscription mock
    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub

    # Mock messages to fetch
    # Message 1: invalid json
    msg1 = AsyncMock()
    msg1.data = b"invalid json"

    # Message 2: valid payload with non-existing task
    msg2 = AsyncMock()
    msg2.data = json.dumps(
        {
            "id": "123",
            "name": "non_existing_task",
            "args": [],
            "kwargs": {},
            "trace_context": {},
        }
    ).encode()

    # Message 3: valid payload with existing task
    msg3 = AsyncMock()
    msg3.data = json.dumps(
        {
            "id": "456",
            "name": "test.run_worker_task",
            "args": [100],
            "kwargs": {},
            "trace_context": {},
        }
    ).encode()

    # Mock fetch to return batches, then raise CancelledError to stop the loop
    loop_count = 0

    async def mock_fetch(batch_size, timeout=5):
        nonlocal loop_count
        loop_count += 1
        if loop_count == 1:
            return [msg1, msg2, msg3]
        raise asyncio.CancelledError()

    mock_sub.fetch = mock_fetch

    # Mock set_app container
    mock_app = MagicMock()
    mock_app.state = MagicMock()
    # Dishka container mock
    mock_container = MagicMock()
    async_context = AsyncMock()
    mock_container.return_value = async_context
    mock_app.state.dishka_container = mock_container
    set_app(mock_app)

    # Patch wrap_injection to just return the handler unmodified for testing simplicity
    with patch("dishka.integrations.base.wrap_injection", lambda func, **kwargs: func):
        try:
            await broker.run_worker()
        except asyncio.CancelledError:
            pass

        # Verification:
        # msg1 should have been acked (invalid json)
        msg1.ack.assert_called_once()
        # msg2 should have term() called (no handler registered)
        msg2.term.assert_called_once()
        # msg3 should have been executed and acked
        assert task_called_with == 100
        msg3.ack.assert_called_once()
