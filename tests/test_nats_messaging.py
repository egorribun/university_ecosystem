from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nats_messaging import NatsMessage, NatsService, get_nats_service


@pytest.mark.anyio
async def test_nats_message_json_decoding():
    msg = NatsMessage(subject="test", data=b'{"key": "value"}')
    assert msg.json() == {"key": "value"}


@pytest.mark.anyio
async def test_nats_service_connect_success():
    service = NatsService(
        servers="nats://localhost:4222",
        name="test-service",
        auth_token="file-token",
    )
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
            token="file-token",
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


def test_get_nats_service():
    s1 = get_nats_service()
    s2 = get_nats_service()
    assert s1 is s2
