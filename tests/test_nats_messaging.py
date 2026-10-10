import uuid
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


@pytest.fixture
async def connected_nats(monkeypatch):
    client = MagicMock()
    client.is_connected = True
    client.publish = AsyncMock()
    client.drain = AsyncMock()
    monkeypatch.setattr("nats.connect", AsyncMock(return_value=client))
    service = NatsService()
    await service.connect()
    return service, client


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "msg_id", "expected_id"),
    [
        ({"id": "domain", "event_id": "event"}, "explicit", "explicit"),
        ({"id": "domain", "event_id": "event"}, None, "domain"),
        ({"id": "", "event_id": "event"}, None, "event"),
        ({"event_id": 42}, None, "42"),
        (b"raw-event", "explicit", "explicit"),
    ],
    ids=["explicit", "payload-id", "event-id", "numeric-id", "bytes"],
)
async def test_publish_preserves_payload_and_copies_headers(
    connected_nats, payload, msg_id, expected_id
):
    service, client = connected_nats
    headers = {"Trace-Id": "trace-123", "Nats-Msg-Id": "caller-header"}

    await service.publish("events.created", payload, headers=headers, msg_id=msg_id)

    client.publish.assert_awaited_once()
    call = client.publish.await_args
    assert call.args[0] == "events.created"
    emitted = call.args[1]
    if isinstance(payload, dict):
        assert NatsMessage(subject=call.args[0], data=emitted).json() == payload
    else:
        assert emitted == payload
    assert call.kwargs["headers"] == {
        "Trace-Id": "trace-123",
        "Nats-Msg-Id": expected_id,
    }
    assert headers == {"Trace-Id": "trace-123", "Nats-Msg-Id": "caller-header"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload", [{"message": "Привет"}, b"raw-event"], ids=["dict", "bytes"]
)
async def test_publish_generates_distinct_deduplication_ids(connected_nats, payload):
    service, client = connected_nats

    await service.publish("events.created", payload)
    await service.publish("events.created", payload)

    emitted_ids = [
        uuid.UUID(call.kwargs["headers"]["Nats-Msg-Id"])
        for call in client.publish.await_args_list
    ]
    assert len(emitted_ids) == 2
    assert all(value.version == 4 for value in emitted_ids)
    assert emitted_ids[0] != emitted_ids[1]


@pytest.mark.anyio
async def test_publish_rejects_unserializable_payload_before_transport(connected_nats):
    service, client = connected_nats

    with pytest.raises(TypeError):
        await service.publish("events.created", {"unsupported": object()})

    client.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_propagates_transport_failure(connected_nats):
    service, client = connected_nats
    client.publish.side_effect = ConnectionError("transport unavailable")

    with pytest.raises(ConnectionError, match="transport unavailable"):
        await service.publish("events.created", b"raw-event", msg_id="retryable-id")

    client.publish.assert_awaited_once_with(
        "events.created", b"raw-event", headers={"Nats-Msg-Id": "retryable-id"}
    )


@pytest.mark.anyio
async def test_publish_and_subscribe_require_connection():
    service = NatsService()
    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.publish("events.created", b"raw-event")
    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.subscribe("events.created", AsyncMock())


@pytest.mark.anyio
async def test_close_without_subscriptions_drains_once(connected_nats):
    service, client = connected_nats

    await service.close()
    await service.close()

    client.drain.assert_awaited_once_with()
    assert service.is_connected is False
