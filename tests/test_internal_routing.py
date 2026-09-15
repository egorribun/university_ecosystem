from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.internal_access import InternalAccessMiddleware


@pytest.mark.asyncio
async def test_internal_routes_absent_from_openapi(root_client: AsyncClient):
    response = await root_client.get("/api/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    paths = schema.get("paths", {})
    for prefix in INTERNAL_ROUTE_PREFIXES:
        leaked = [path for path in paths if path.startswith(prefix)]
        assert not leaked, leaked


@pytest.mark.asyncio
async def test_internal_routes_require_token(root_client: AsyncClient):
    # Patch _is_allowed_ip_from_scope to return False, simulating request from external IP
    with patch.object(
        InternalAccessMiddleware, "_is_allowed_ip_from_scope", return_value=False
    ):
        response = await root_client.get("/api/v1/admin/dlq/stats")

        assert response.status_code == 403
        assert response.json()["detail"] == "Internal API access denied"


def test_chat_participant_endpoint_is_the_only_public_chat_internal_prefix():
    """The ws-hub callback is internal without covering the public chat API."""

    assert "/api/v1/chat/check-participant" in INTERNAL_ROUTE_PREFIXES
    assert "/api/v1/chat" not in INTERNAL_ROUTE_PREFIXES


@pytest.mark.asyncio
async def test_chat_participant_endpoint_denies_external_client(
    root_client: AsyncClient,
):
    """An external caller cannot reach the participant authorization handler."""

    with patch.object(
        InternalAccessMiddleware, "_is_allowed_ip_from_scope", return_value=False
    ):
        response = await root_client.get(
            "/api/v1/chat/check-participant",
            params={
                "user_id": "00000000-0000-0000-0000-000000000001",
                "room_id": "00000000-0000-0000-0000-000000000002",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Internal API access denied"
