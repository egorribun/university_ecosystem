import json
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from elastic_transport import ApiResponseMeta, BaseAsyncNode, HttpHeaders
from elastic_transport._node._base import NodeApiResponse
from elasticsearch import ApiError, AsyncElasticsearch, NotFoundError

from app.services.search import SearchService


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


class _SearchDeleteNode(BaseAsyncNode):
    """Concrete-index DELETE routes; the real SDK handles HTTP error responses.

    https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-delete
    https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete
    """

    def __init__(self, config):
        super().__init__(config)
        self.documents = {"unrelated": {"keep": {"title": "Keep"}}}
        self.failure_status = None
        self.request_count = 0

    def respond(self, status, body):
        return NodeApiResponse(
            ApiResponseMeta(
                status=status,
                http_version="1.1",
                headers=HttpHeaders(
                    {
                        "content-type": "application/json",
                        "x-elastic-product": "Elasticsearch",
                    }
                ),
                duration=0,
                node=self.config,
            ),
            json.dumps(body).encode(),
        )

    async def perform_request(self, method, target, **kwargs):
        self.request_count += 1
        if self.failure_status is not None:
            return self.respond(
                self.failure_status,
                {
                    "error": {"type": "unavailable", "reason": "Deletion failed"},
                    "status": self.failure_status,
                },
            )
        assert method == "DELETE"
        url = urlsplit(target)
        parts = [unquote(part) for part in url.path.strip("/").split("/")]
        index = parts[0]
        if len(parts) == 1:
            ignore_missing = parse_qs(url.query).get("ignore_unavailable") == ["true"]
            if index in self.documents or ignore_missing:
                self.documents.pop(index, None)
                return self.respond(200, {"acknowledged": True})
        else:
            assert len(parts) == 3 and parts[1] == "_doc"
            if index in self.documents:
                document_id = parts[2]
                found = self.documents[index].pop(document_id, None) is not None
                return self.respond(
                    200 if found else 404,
                    {
                        "_index": index,
                        "_id": document_id,
                        "_version": 2,
                        "_shards": {"total": 1, "successful": 1, "failed": 0},
                        "result": "deleted" if found else "not_found",
                    },
                )
        return self.respond(
            404,
            {
                "error": {
                    "type": "index_not_found_exception",
                    "reason": f"no such index [{index}]",
                },
                "status": 404,
            },
        )

    async def close(self):
        pass


@pytest.fixture
async def deletion_service():
    # BaseAsyncNode has no socket implementation: requests stay inside this process.
    service = SearchService()
    service._client = AsyncElasticsearch(
        "http://elasticsearch.invalid:9200", node_class=_SearchDeleteNode
    )
    node = service.client.transport.node_pool.all()[0]
    try:
        yield service, node
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("initially_present", [False, True], ids=["absent", "present"])
async def test_delete_index_is_idempotent(deletion_service, initially_present):
    service, node = deletion_service
    if initially_present:
        node.documents["news-rebuild-old"] = {"obsolete": {"title": "Old"}}

    await service.delete_index("news-rebuild-old")
    await service.delete_index("news-rebuild-old")

    assert node.documents == {"unrelated": {"keep": {"title": "Keep"}}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_state", ["absent-index", "absent-document", "present"]
)
async def test_delete_document_is_idempotent(deletion_service, initial_state):
    service, node = deletion_service
    if initial_state != "absent-index":
        node.documents["news"] = {"keep": {"title": "Keep"}}
    if initial_state == "present":
        node.documents["news"]["obsolete"] = {"title": "Old"}

    await service.delete_document("news", "obsolete")
    await service.delete_document("news", "obsolete")

    expected = {"unrelated": {"keep": {"title": "Keep"}}}
    if initial_state != "absent-index":
        expected["news"] = {"keep": {"title": "Keep"}}
    assert node.documents == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["index", "document"])
@pytest.mark.parametrize("status", [403, 503])
async def test_search_deletion_preserves_non404_failures(
    deletion_service, operation, status
):
    service, node = deletion_service
    node.documents["news-rebuild-old"] = {"obsolete": {"title": "Old"}}
    before = deepcopy(node.documents)
    node.failure_status = status

    with pytest.raises(ApiError) as raised:
        if operation == "index":
            await service.delete_index("news-rebuild-old")
        else:
            await service.delete_document("news-rebuild-old", "obsolete")

    assert raised.value.status_code == status
    assert node.documents == before
    if status == 503:
        assert node.request_count > 1
    else:
        assert node.request_count == 1
