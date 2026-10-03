import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ws_hub_client import WsHubClient, invalidate_ws_hub_cache


@pytest.fixture
def ws_client(monkeypatch):
    # Reset singleton
    import app.services.ws_hub_client as module

    module._client = None

    mock_settings = MagicMock(ws_hub_internal_secret="testsecret")
    monkeypatch.setattr("app.core.config.settings", mock_settings)

    mock_broker = AsyncMock()
    monkeypatch.setattr("app.core.nats_broker.broker", mock_broker)

    return WsHubClient(), mock_broker


@pytest.mark.asyncio
async def test_invalidate_cache_success(ws_client, monkeypatch):
    client, mock_broker = ws_client

    mock_time = MagicMock(return_value=1234567890)
    monkeypatch.setattr("app.services.ws_hub_client.time.time_ns", mock_time)

    user_id = uuid.uuid4()
    room_id = uuid.uuid4()

    await client.invalidate_cache(user_id, room_id)

    mock_broker.publish.assert_called_once()
    args = mock_broker.publish.call_args[0]
    assert args[0] == "cache.invalidate"

    payload = args[1]
    assert "data" in payload
    assert "signature" in payload
    assert payload["data"]["user_id"] == str(user_id)
    assert payload["data"]["room_id"] == str(room_id)
    assert payload["data"]["timestamp"] == 1234567890
    assert "evict_room" not in payload["data"]


@pytest.mark.asyncio
async def test_invalidate_cache_can_request_room_eviction_with_stable_event_id(
    ws_client,
):
    client, mock_broker = ws_client

    await client.invalidate_cache(
        "user-1",
        "room-1",
        evict_room=True,
        event_id="stored-event-1",
        raise_on_failure=True,
    )

    args, kwargs = mock_broker.publish.call_args
    assert args[0] == "cache.invalidate"
    assert args[1]["data"]["evict_room"] is True
    signed_data = json.dumps(
        args[1]["data"], sort_keys=True, separators=(",", ":")
    ).encode()
    expected_signature = hmac.new(
        b"testsecret", signed_data, hashlib.sha256
    ).hexdigest()
    assert args[1]["signature"] == expected_signature
    assert kwargs["msg_id"] == "stored-event-1"


@pytest.mark.asyncio
async def test_eviction_signature_matches_shared_go_wire_fixture(
    ws_client, monkeypatch
):
    client, mock_broker = ws_client
    monkeypatch.setattr("app.services.ws_hub_client.time.time_ns", lambda: 1234)

    await client.invalidate_cache(
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        evict_room=True,
    )

    payload = mock_broker.publish.call_args.args[1]
    assert (
        payload["signature"]
        == (
            "478e2845bae80bce3435d37b1087b0e32b32087db6c702a4ad2aaa58a6bdfdc1"  # pragma: allowlist secret -- deterministic public HMAC test vector
        )
    )


@pytest.mark.asyncio
async def test_invalidate_cache_propagates_final_failure_for_durable_delivery(
    ws_client, monkeypatch
):
    client, mock_broker = ws_client
    mock_broker.publish.side_effect = ConnectionError("NATS unavailable")
    monkeypatch.setattr("app.services.ws_hub_client.asyncio.sleep", AsyncMock())

    with pytest.raises(ConnectionError, match="NATS unavailable"):
        await client.invalidate_cache(
            "user-1", "room-1", evict_room=True, raise_on_failure=True
        )

    assert mock_broker.publish.call_count == 2


@pytest.mark.asyncio
async def test_invalidate_cache_retry(ws_client, monkeypatch):
    client, mock_broker = ws_client

    # Fail first time, succeed second
    mock_broker.publish.side_effect = [ConnectionError("err"), None]

    mock_sleep = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.asyncio.sleep", mock_sleep)

    await client.invalidate_cache("u1", "r1")

    assert mock_broker.publish.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_cache_all_fail(ws_client, monkeypatch):
    client, mock_broker = ws_client

    mock_broker.publish.side_effect = ConnectionError("err")

    mock_sleep = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.asyncio.sleep", mock_sleep)

    mock_counter = MagicMock()
    monkeypatch.setattr(
        "app.services.ws_hub_client._INVALIDATION_FAILURES", mock_counter
    )

    await client.invalidate_cache("u1", "r1")

    assert mock_broker.publish.call_count == 2
    mock_counter.inc.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_ws_hub_cache(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client._get_client", lambda: mock_client)

    await invalidate_ws_hub_cache("u1", "r1")

    mock_client.invalidate_cache.assert_called_once_with(user_id="u1", room_id="r1")


@pytest.mark.asyncio
async def test_invalidate_ws_hub_cache_forwards_room_eviction_options(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client._get_client", lambda: mock_client)

    await invalidate_ws_hub_cache(
        "u1",
        "r1",
        evict_room=True,
        event_id="evt-1",
        raise_on_failure=True,
    )

    mock_client.invalidate_cache.assert_awaited_once_with(
        user_id="u1",
        room_id="r1",
        evict_room=True,
        event_id="evt-1",
        raise_on_failure=True,
    )


def test_get_client(monkeypatch):
    import app.services.ws_hub_client as module

    module._client = None

    mock_settings = MagicMock(ws_hub_internal_secret="testsecret")
    monkeypatch.setattr("app.core.config.settings", mock_settings)
    mock_broker = AsyncMock()
    monkeypatch.setattr("app.core.nats_broker.broker", mock_broker)

    c1 = module._get_client()
    c2 = module._get_client()

    assert c1 is c2
    assert isinstance(c1, WsHubClient)
