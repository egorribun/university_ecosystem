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
    monkeypatch.setattr("app.services.ws_hub_client._INVALIDATION_FAILURES", mock_counter)
    
    await client.invalidate_cache("u1", "r1")
    
    assert mock_broker.publish.call_count == 2
    mock_counter.inc.assert_called_once()

@pytest.mark.asyncio
async def test_invalidate_ws_hub_cache(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client._get_client", lambda: mock_client)
    
    await invalidate_ws_hub_cache("u1", "r1")
    
    mock_client.invalidate_cache.assert_called_once_with(user_id="u1", room_id="r1")

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
