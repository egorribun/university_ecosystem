import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_root_endpoint(root_client):
    response = await root_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthcheck(root_client):
    response = await root_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness(root_client):
    response = await root_client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
