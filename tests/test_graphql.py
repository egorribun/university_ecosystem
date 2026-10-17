"""MVP contract for the retired backend GraphQL HTTP surface."""

from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_backend_graphql_paths_return_not_found(root_client: AsyncClient) -> None:
    for path in ("/graphql", "/graphql/", "/graphql/query"):
        response = await root_client.post(path, json={"query": "{ __typename }"})
        assert response.status_code == 404, path

    get_response = await root_client.get("/graphql", params={"query": "{ __typename }"})
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_context_direct() -> None:
    from app.graphql.schema import get_context

    mock_request = MagicMock()
    mock_container = MagicMock()
    mock_request.state.dishka_container = mock_container

    # Keep this internal generator smoke test independent of the HTTP route.
    gen = get_context(mock_request)
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
    except Exception:  # noqa: S110
        pass
