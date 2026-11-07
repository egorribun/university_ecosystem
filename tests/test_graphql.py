"""MVP contract for the retired backend GraphQL HTTP surface."""

from unittest.mock import AsyncMock, MagicMock, call

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
    from app.auth.rbac import PermissionChecker
    from app.core.protocols import AsyncDatabaseSession
    from app.graphql.context import GraphQLContext
    from app.graphql.dataloaders import DataLoaderRegistry
    from app.graphql.schema import get_context

    mock_request = MagicMock()
    mock_container = MagicMock()
    mock_request.state.dishka_container = mock_container
    mock_request.headers = {}
    mock_request.app.dependency_overrides = {}
    session = MagicMock(name="session")
    checker = MagicMock(name="permission_checker")
    mock_container.get = AsyncMock(side_effect=[session, checker])

    # Keep this internal generator smoke test independent of the HTTP route.
    gen = get_context(mock_request)
    context = await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert isinstance(context, GraphQLContext)
    assert context.session is session
    assert isinstance(context.loaders, DataLoaderRegistry)
    assert context.loaders._session is session
    assert context.checker is checker
    assert context.current_user is None
    assert context.request is mock_request
    assert mock_container.get.await_args_list == [
        call(AsyncDatabaseSession),
        call(PermissionChecker),
    ]
