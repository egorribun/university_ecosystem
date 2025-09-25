import pytest

pytestmark = pytest.mark.anyio("asyncio")


async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthcheck(async_client):
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness(async_client):
    response = await async_client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
