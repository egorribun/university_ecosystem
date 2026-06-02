import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_v1_prefix(async_client: AsyncClient):
    """Test that API v1 prefix is working."""
    # We use /api/v1/news as a sample endpoint
    response = await async_client.get(
        "http://testserver/api/v1/news",
        headers={"X-Disable-Query-Budget": "true"},
    )
    # Should be 200 (public endpoint) or 401/403, but NOT 404
    assert response.status_code != 404


@pytest.mark.asyncio
async def test_root_endpoints(async_client: AsyncClient):
    """Test that root endpoints are available."""
    response = await async_client.get("http://testserver/healthz")
    if response.status_code != 200:
        pass
    assert response.status_code == 200
    assert response.json()["db"] == "ok"

    response = await async_client.get("http://testserver/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_websocket_endpoint_path(app):
    """Test WebSocket endpoint path."""
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/chat"):
            pass
    assert exc.value.code in (1008, 4001)
