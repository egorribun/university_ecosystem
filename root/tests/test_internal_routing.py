import pytest
from httpx import AsyncClient

from app.api.internal import INTERNAL_ROUTE_PREFIXES


@pytest.mark.anyio
async def test_internal_routes_absent_from_openapi(root_client: AsyncClient):
    response = await root_client.get("/api/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    paths = schema.get("paths", {})
    for prefix in INTERNAL_ROUTE_PREFIXES:
        leaked = [path for path in paths if path.startswith(prefix)]
        assert not leaked, leaked


@pytest.mark.anyio
async def test_internal_routes_require_token(root_client: AsyncClient):
    response = await root_client.get("/api/v1/notifications/admin/dead-letter")

    assert response.status_code == 403
    assert response.json()["detail"] == "Internal API access denied"
