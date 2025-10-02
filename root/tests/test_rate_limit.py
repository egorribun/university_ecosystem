import pytest


@pytest.mark.anyio
async def test_rate_limit_per_ip(async_client):
    for _ in range(60):
        response = await async_client.get("/healthz")
        assert response.status_code == 200
    response = await async_client.get("/healthz")
    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests"
    assert response.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_rate_limit_per_token(async_client):
    headers = {"Authorization": "Bearer token-a"}
    for _ in range(60):
        response = await async_client.get("/healthz", headers=headers)
        assert response.status_code == 200
    blocked = await async_client.get("/healthz", headers=headers)
    assert blocked.status_code == 429

    other = await async_client.get("/healthz", headers={"Authorization": "Bearer token-b"})
    assert other.status_code == 200
