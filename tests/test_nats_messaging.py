from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nats_messaging import NatsMessage, NatsService, get_nats_service


@pytest.mark.anyio
async def test_nats_message_json_decoding():
    msg = NatsMessage(subject="test", data=b'{"key": "value"}')
    assert msg.json() == {"key": "value"}


@pytest.mark.anyio
async def test_nats_service_connect_success():
    service = NatsService(servers="nats://localhost:4222", name="test-service")
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_js = AsyncMock()
    mock_client.jetstream = MagicMock(return_value=mock_js)

    with patch("nats.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_client
        await service.connect()

        mock_connect.assert_called_once_with(
            servers=["nats://localhost:4222"],
            name="test-service",
            reconnect_time_wait=2,
            max_reconnect_attempts=-1,
        )
        assert service._client is mock_client
        assert service._js is mock_js
        assert service.is_connected is True

        # Idempotence: connect again returns early
        await service.connect()
        mock_connect.assert_called_once()


@pytest.mark.anyio
async def test_nats_service_close():
    service = NatsService()
    mock_client = AsyncMock()
    service._client = mock_client
    service._js = AsyncMock()

    mock_sub = AsyncMock()
    service._subscriptions.append(mock_sub)

    await service.close()
    mock_sub.unsubscribe.assert_called_once()
    mock_client.drain.assert_called_once()
    assert len(service._subscriptions) == 0
    assert service._client is None
    assert service._js is None


@pytest.mark.anyio
async def test_nats_service_ensure_stream():
    service = NatsService()
    mock_js = AsyncMock()
    service._js = mock_js

    # Test stream setup success
    await service.ensure_stream(name="test-stream", subjects=["test.>"])
    mock_js.add_stream.assert_called_once()
    kwargs = mock_js.add_stream.call_args.kwargs
    assert kwargs["config"].name == "test-stream"
    assert kwargs["config"].subjects == ["test.>"]

    # Test error handling when not connected
    service._js = None
    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.ensure_stream(name="test", subjects=[])


@pytest.mark.anyio
async def test_nats_service_publish_and_jetstream():
    service = NatsService()
    mock_client = AsyncMock()
    mock_js = AsyncMock()
    service._client = mock_client
    service._js = mock_js

    # Test Core NATS publish bytes
    await service.publish("test.sub", b"raw-bytes")
    mock_client.publish.assert_called_once_with("test.sub", b"raw-bytes", headers=None)

    # Test Core NATS publish dict
    mock_client.publish.reset_mock()
    await service.publish("test.sub", {"hello": "world"})
    mock_client.publish.assert_called_once()
    args = mock_client.publish.call_args.args
    assert args[0] == "test.sub"
    assert b"hello" in args[1]

    # Test JetStream publish
    await service.publish_jetstream("test.sub", {"foo": "bar"})
    mock_js.publish.assert_called_once()


@pytest.mark.anyio
async def test_nats_service_subscribe():
    service = NatsService()
    mock_client = AsyncMock()
    service._client = mock_client

    handler_called = None

    async def my_handler(msg: NatsMessage):
        nonlocal handler_called
        handler_called = msg.json()

    # Simulate sub registration
    async def fake_subscribe(subject, queue, cb):
        # Trigger callback immediately with a mock NATS message
        mock_msg = MagicMock()
        mock_msg.subject = subject
        mock_msg.data = b'{"val": 123}'
        mock_msg.headers = None
        await cb(mock_msg)
        return AsyncMock()

    mock_client.subscribe.side_effect = fake_subscribe

    await service.subscribe("test.subject", my_handler, queue="test-group")
    assert handler_called == {"val": 123}
    assert len(service._subscriptions) == 1


@pytest.mark.anyio
async def test_nats_service_subscribe_jetstream():
    service = NatsService()
    mock_js = AsyncMock()
    service._js = mock_js

    handler_called = None

    async def my_handler(msg: NatsMessage):
        nonlocal handler_called
        handler_called = msg.subject
        if msg.subject == "error":
            raise ValueError("handler failed")

    async def fake_subscribe_js(subject, stream, durable, config, cb):
        # 1. Successful message
        mock_msg1 = AsyncMock()
        mock_msg1.subject = "success"
        mock_msg1.data = b"ok"
        await cb(mock_msg1)
        mock_msg1.ack.assert_called_once()

        # 2. Failing message
        mock_msg2 = AsyncMock()
        mock_msg2.subject = "error"
        mock_msg2.data = b"err"
        await cb(mock_msg2)
        mock_msg2.nak.assert_called_once()

        return AsyncMock()

    mock_js.subscribe.side_effect = fake_subscribe_js

    await service.subscribe_jetstream(
        stream="test-stream",
        subject="test.subject",
        handler=my_handler,
        durable="test-durable",
    )
    assert len(service._subscriptions) == 1
    assert handler_called == "error"


def test_get_nats_service():
    s1 = get_nats_service()
    s2 = get_nats_service()
    assert s1 is s2
