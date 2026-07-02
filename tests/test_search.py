from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from elasticsearch import NotFoundError

from app.services.search import (
    SearchService,
    get_search_service,
)


@pytest.mark.anyio
async def test_search_service_lazy_client():
    service = SearchService(hosts="http://localhost:9200", http_auth=("user", "pass"))
    assert service._client is None

    # Accessing client property should initialize it
    with patch("app.services.search.AsyncElasticsearch") as mock_ae:
        client = service.client
        assert client is not None
        mock_ae.assert_called_once_with(
            hosts=["http://localhost:9200"], http_auth=("user", "pass")
        )
        assert service._client is client

    # Client without http_auth
    service_no_auth = SearchService(hosts="http://localhost:9200", http_auth=None)
    with patch("app.services.search.AsyncElasticsearch") as mock_ae_no_auth:
        client_no_auth = service_no_auth.client
        assert client_no_auth is not None
        mock_ae_no_auth.assert_called_once_with(hosts=["http://localhost:9200"])


@pytest.mark.anyio
async def test_search_service_close():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    await service.close()
    mock_client.close.assert_called_once()
    assert service._client is None

    # Close when client is already None
    service_no_client = SearchService()
    await service_no_client.close()
    assert service_no_client._client is None


@pytest.mark.anyio
async def test_search_service_ensure_index():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    # Index does not exist
    mock_client.indices.exists.return_value = False
    await service.ensure_index("test-index", mappings={"foo": "bar"})

    mock_client.indices.exists.assert_called_once_with(index="test-index")
    mock_client.indices.create.assert_called_once_with(
        index="test-index", body={"mappings": {"foo": "bar"}}
    )

    # Index does not exist and no mappings provided
    mock_client.indices.exists.reset_mock()
    mock_client.indices.create.reset_mock()
    mock_client.indices.exists.return_value = False
    await service.ensure_index("test-index-no-mappings", mappings=None)
    mock_client.indices.exists.assert_called_once_with(index="test-index-no-mappings")
    mock_client.indices.create.assert_called_once_with(
        index="test-index-no-mappings", body={}
    )

    # Index exists
    mock_client.indices.exists.reset_mock()
    mock_client.indices.create.reset_mock()
    mock_client.indices.exists.return_value = True

    await service.ensure_index("test-index")
    mock_client.indices.exists.assert_called_once_with(index="test-index")
    mock_client.indices.create.assert_not_called()


@pytest.mark.anyio
async def test_search_service_index_document():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    body = {"title": "Hello"}
    await service.index_document("test-index", "doc-123", body)
    mock_client.index.assert_called_once_with(
        index="test-index", id="doc-123", body=body
    )


@pytest.mark.anyio
async def test_search_service_bulk_index():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    documents = [{"id": "1", "val": "A"}, {"id": "2", "val": "B"}]

    with patch("app.services.search.async_bulk", new_callable=AsyncMock) as mock_bulk:

        async def mock_bulk_consume(client, actions, **kwargs):
            # Consume the generator to ensure the inner generate_actions function is executed
            list(actions)
            return 2, []

        mock_bulk.side_effect = mock_bulk_consume
        success, failed = await service.bulk_index("test-index", documents)

        assert success == 2
        assert failed == 0
        mock_bulk.assert_called_once()


@pytest.mark.anyio
async def test_search_service_delete_document():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    # Success case
    await service.delete_document("test-index", "doc-123")
    mock_client.delete.assert_called_once_with(index="test-index", id="doc-123")

    # NotFoundError should be caught and ignored
    mock_client.delete.reset_mock()
    mock_client.delete.side_effect = NotFoundError(
        meta=MagicMock(), body="{}", message="not found"
    )
    await service.delete_document("test-index", "doc-123")
    mock_client.delete.assert_called_once()


@pytest.mark.anyio
async def test_search_service_search_validation_and_execution():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    # Enforce fields validation
    with pytest.raises(ValueError, match="requires an explicit 'fields' list"):
        await service.search("test-index", "query", fields=[])

    # Successful search return
    mock_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": "doc-1",
                    "_score": 1.5,
                    "_source": {"title": "Title"},
                    "highlight": {"title": ["<mark>Title</mark>"]},
                }
            ],
        }
    }

    result = await service.search(
        "test-index", "query", fields=["title"], size=150, offset=20000
    )
    assert result["total"] == 1
    assert len(result["hits"]) == 1
    assert result["hits"][0]["id"] == "doc-1"
    assert result["hits"][0]["score"] == 1.5
    assert result["hits"][0]["highlights"] == {"title": ["<mark>Title</mark>"]}

    # Clamping assertion: size should be capped at 100, from capped at 10000
    mock_client.search.assert_called_once()
    body = mock_client.search.call_args.kwargs["body"]
    assert body["size"] == 100
    assert body["from"] == 10000

    # Search with highlight=False
    mock_client.search.reset_mock()
    await service.search("test-index", "query", fields=["title"], highlight=False)
    assert "highlight" not in mock_client.search.call_args.kwargs["body"]


@pytest.mark.anyio
async def test_search_service_suggest():
    service = SearchService()
    mock_client = AsyncMock()
    service._client = mock_client

    mock_client.search.return_value = {
        "suggest": {
            "suggestions": [
                {
                    "options": [
                        {"text": "suggest-1"},
                        {"text": "suggest-2"},
                    ]
                }
            ]
        }
    }

    res = await service.suggest("test-index", "prefix-q", size=30)
    assert res == ["suggest-1", "suggest-2"]

    # Capped size checks (max 20)
    body = mock_client.search.call_args.kwargs["body"]
    assert body["suggest"]["suggestions"]["completion"]["size"] == 20

    # Empty suggestions branch cover
    mock_client.search.return_value = {}
    res_empty = await service.suggest("test-index", "prefix-q")
    assert res_empty == []


def test_get_search_service():
    with pytest.deprecated_call():
        service = get_search_service()
        assert isinstance(service, SearchService)
