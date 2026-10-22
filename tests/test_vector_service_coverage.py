import math
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import registry

from app.core.config import settings
from app.services.vector_service import SemanticSearchUnavailableError, VectorService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def vector_service(mock_db):
    with patch.object(settings, "embedding_api_base", "https://93.184.216.34"):
        service = VectorService(mock_db)
    return service


@pytest.mark.asyncio
async def test_get_embedding_disabled(vector_service):
    with patch.object(settings, "semantic_search_enabled", False):
        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")


@pytest.mark.asyncio
async def test_get_embedding_no_api_key(vector_service):
    # Ensure enabled but no key
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", None),
    ):
        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")


@pytest.mark.asyncio
async def test_get_embedding_success(vector_service):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
    ):
        # Mock the internal client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1] * settings.embedding_dimensions}]
        }
        mock_response.raise_for_status = MagicMock()

        vector_service._client.post = AsyncMock(return_value=mock_response)

        embedding = await vector_service.get_embedding("test")
        assert len(embedding) == settings.embedding_dimensions
        assert embedding[0] == 0.1


@pytest.mark.asyncio
async def test_get_embedding_failure(vector_service, caplog):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
    ):
        vector_service._client.post = AsyncMock(
            side_effect=ConnectionError("provider-secret-marker")
        )

        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")
        assert "provider-secret-marker" not in caplog.text


@pytest.mark.asyncio
async def test_search_similar_with_scores_disabled(vector_service):
    with patch.object(settings, "semantic_search_enabled", False):
        results = await vector_service.search_similar_with_scores(MagicMock(), [0.1])
        assert results == []


@pytest.mark.asyncio
async def test_search_similar_with_scores_empty_embedding(vector_service):
    with patch.object(settings, "semantic_search_enabled", True):
        results = await vector_service.search_similar_with_scores(MagicMock(), [])
        assert results == []


@pytest.mark.asyncio
async def test_search_similar_with_scores_success(vector_service, mock_db):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch("app.services.vector_service.select") as _mock_select,
    ):
        # Mock model
        mock_model = MagicMock()
        # Mock distance calculation
        mock_distance = MagicMock()

        # The SQL query compares the labeled score to the threshold and finite bounds.
        mock_score_column = MagicMock()
        mock_score_column.desc.return_value = mock_score_column
        mock_score_column.__ge__ = MagicMock(return_value=MagicMock())
        mock_score_column.__gt__ = MagicMock(return_value=MagicMock())
        mock_score_column.__lt__ = MagicMock(return_value=MagicMock())

        # When 1.0 - distance is called:
        mock_sub_result = MagicMock()
        mock_sub_result.label.return_value = mock_score_column
        mock_distance.__rsub__ = MagicMock(return_value=mock_sub_result)

        mock_model.embedding.cosine_distance.return_value = mock_distance

        # Mock DB result
        mock_result = MagicMock()
        mock_obj = MagicMock()
        mock_score = 0.8
        mock_result.all.return_value = [(mock_obj, mock_score)]
        mock_db.execute.return_value = mock_result

        results = await vector_service.search_similar_with_scores(mock_model, [0.1])
        assert len(results) == 1
        assert results[0][0] == mock_obj
        assert results[0][1] == 0.8
        mock_db.execute.assert_called()


@pytest.mark.asyncio
async def test_search_similar_wrapper(vector_service):
    with patch.object(
        vector_service, "search_similar_with_scores", new_callable=AsyncMock
    ) as mock_search:
        mock_obj = MagicMock()
        mock_search.return_value = [(mock_obj, 0.9)]

        results = await vector_service.search_similar(MagicMock(), [0.1])

        assert len(results) == 1
        assert results[0] == mock_obj
        mock_search.assert_called_once()


@pytest.mark.asyncio
async def test_close(vector_service):
    vector_service._client.aclose = AsyncMock()
    await vector_service.close()
    vector_service._client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_with_scores_no_attributes(vector_service, mock_db):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch("app.services.vector_service.select") as _mock_select,
    ):

        class SparseModel:
            embedding = MagicMock()

        mock_model = SparseModel()
        mock_distance = MagicMock()
        mock_score_column = MagicMock()
        mock_score_column.desc.return_value = mock_score_column
        mock_score_column.__ge__ = MagicMock(return_value=MagicMock())
        mock_score_column.__gt__ = MagicMock(return_value=MagicMock())
        mock_score_column.__lt__ = MagicMock(return_value=MagicMock())

        mock_sub_result = MagicMock()
        mock_sub_result.label.return_value = mock_score_column
        mock_distance.__rsub__ = MagicMock(return_value=mock_sub_result)
        mock_model.embedding.cosine_distance.return_value = mock_distance

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        results = await vector_service.search_similar_with_scores(mock_model, [0.1])
        assert results == []


@pytest.mark.asyncio
async def test_vector_service_context_manager(mock_db):
    with patch("app.services.vector_service.validate_url_not_internal_async"):
        async with VectorService(mock_db) as service:
            service._client.aclose = AsyncMock()
            assert service.db is mock_db
        service._client.aclose.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_cls",
    [
        ValueError("Invalid JSON response"),
        TimeoutError("Request timed out"),
        httpx.TransportError("Connection failed"),
        httpx.HTTPStatusError(
            "Status error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        ),
    ],
)
async def test_get_embedding_various_exceptions(vector_service, exception_cls):
    """Provider failures must surface as semantic-search unavailability."""
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
    ):
        vector_service._client.post = AsyncMock(side_effect=exception_cls)

        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")


@pytest.mark.asyncio
async def test_search_similar_with_scores_model_attributes(vector_service, mock_db):
    """Test that is_active and deleted_at attributes on models are correctly query-filtered."""
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch("app.services.vector_service.select") as mock_select,
    ):

        class RichModel:
            is_active = True
            deleted_at = MagicMock()
            embedding = MagicMock()

        mock_model = RichModel()
        mock_distance = MagicMock()
        mock_score_column = MagicMock()
        mock_score_column.desc.return_value = mock_score_column
        mock_score_column.__ge__ = MagicMock(return_value=MagicMock())
        mock_score_column.__gt__ = MagicMock(return_value=MagicMock())
        mock_score_column.__lt__ = MagicMock(return_value=MagicMock())

        mock_sub_result = MagicMock()
        mock_sub_result.label.return_value = mock_score_column
        mock_distance.__rsub__ = MagicMock(return_value=mock_sub_result)
        mock_model.embedding.cosine_distance.return_value = mock_distance

        # Mock select statement builder chain
        mock_stmt = MagicMock()
        mock_select.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        await vector_service.search_similar_with_scores(mock_model, [0.1])

        # Verify that select was called, and where clauses were applied
        mock_select.assert_called_once()
        assert mock_stmt.where.call_count >= 2


@pytest.mark.asyncio
async def test_vector_service_ssrf_validation(mock_db):
    """Validate at the active request boundary, before any provider POST."""
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
        patch.object(settings, "embedding_api_base", "http://127.0.0.1"),
    ):
        async with VectorService(mock_db) as service:
            service._client.post = AsyncMock()
            with pytest.raises(ValueError, match="SSRF"):
                await service.get_embedding("private")
            service._client.post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,key", [(False, "fake-key"), (True, None)])
async def test_unused_embedding_provider_never_resolves_dns(mock_db, enabled, key):
    with (
        patch.object(settings, "semantic_search_enabled", enabled),
        patch.object(settings, "embedding_api_key", key),
        patch("socket.getaddrinfo", side_effect=AssertionError("Unexpected DNS")),
    ):
        async with VectorService(mock_db) as service:
            service._client.post = AsyncMock()
            with pytest.raises(SemanticSearchUnavailableError):
                await service.get_embedding("unused")
            service._client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_embedding_rejects_zero_provider_vector(vector_service):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
        patch("app.services.vector_service.validate_url_not_internal_async"),
    ):
        response = MagicMock()
        response.json.return_value = {"data": [{"embedding": [0.0, 0.0]}]}
        response.raise_for_status = MagicMock()
        vector_service._client.post = AsyncMock(return_value=response)

        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")


@pytest.mark.asyncio
async def test_get_embedding_rejects_wrong_dimension(vector_service):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
        patch("app.services.vector_service.validate_url_not_internal_async"),
    ):
        response = MagicMock()
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
        response.raise_for_status = MagicMock()
        vector_service._client.post = AsyncMock(return_value=response)

        with pytest.raises(SemanticSearchUnavailableError):
            await vector_service.get_embedding("test")


@pytest.mark.asyncio
async def test_get_embedding_rejects_provider_integer_overflow(monkeypatch):
    real_client = httpx.AsyncClient

    def provider(request):
        return httpx.Response(200, json={"data": [{"embedding": [10**400, 0.25]}]})

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(provider), **kwargs)

    monkeypatch.setattr(settings, "embedding_api_base", "https://93.184.216.34")
    monkeypatch.setattr(settings, "embedding_api_key", "test-provider-key")
    monkeypatch.setattr(settings, "embedding_dimensions", 2)
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr("app.services.vector_service.httpx.AsyncClient", client_factory)
    async with VectorService(AsyncMock()) as service:
        with pytest.raises(
            SemanticSearchUnavailableError,
            match="Semantic search is currently unavailable",
        ):
            await service.get_embedding("research seminar")


@pytest.mark.asyncio
async def test_embedding_request_passes_finite_deadlines_to_http_transport(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def provider(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"embedding": [0.25, 0.75]}]})

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(provider), **kwargs)

    monkeypatch.setattr(settings, "embedding_api_base", "https://93.184.216.34")
    monkeypatch.setattr(settings, "embedding_api_key", "test-provider-key")
    monkeypatch.setattr(settings, "embedding_dimensions", 2)
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr("app.services.vector_service.httpx.AsyncClient", client_factory)
    async with VectorService(AsyncMock()) as service:
        assert await service.get_embedding("research seminar") == [0.25, 0.75]

    assert len(requests) == 1
    deadlines = requests[0].extensions["timeout"]
    for operation in ("connect", "read", "write", "pool"):
        assert deadlines[operation] is not None
        assert 0 < deadlines[operation] <= 10.0


@pytest.mark.asyncio
async def test_search_similar_with_scores_excludes_non_finite_scores(
    vector_service, mock_db
):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch("app.services.vector_service.select"),
    ):
        mock_model = MagicMock()
        mock_score_column = MagicMock()
        mock_score_column.desc.return_value = mock_score_column
        mock_score_column.__ge__ = MagicMock(return_value=MagicMock())
        mock_score_column.__gt__ = MagicMock(return_value=MagicMock())
        mock_score_column.__lt__ = MagicMock(return_value=MagicMock())
        mock_distance = MagicMock()
        mock_sub_result = MagicMock()
        mock_sub_result.label.return_value = mock_score_column
        mock_distance.__rsub__ = MagicMock(return_value=mock_sub_result)
        mock_model.embedding.cosine_distance.return_value = mock_distance

        finite_positive = MagicMock()
        not_a_number = MagicMock()
        positive_infinity = MagicMock()
        negative_infinity = MagicMock()
        finite_zero = MagicMock()
        finite_negative = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (finite_positive, 0.8),
            (not_a_number, float("nan")),
            (positive_infinity, float("inf")),
            (negative_infinity, float("-inf")),
            (finite_zero, 0.0),
            (finite_negative, -0.25),
        ]
        mock_db.execute.return_value = mock_result

        results = await vector_service.search_similar_with_scores(
            mock_model, [0.1], min_score=-1.0
        )

    assert results == [
        (finite_positive, 0.8),
        (finite_zero, 0.0),
        (finite_negative, -0.25),
    ]


@pytest.mark.asyncio
async def test_search_query_excludes_non_finite_scores_before_limit(
    vector_service, mock_db
):
    table = Table(
        "vector_items",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("embedding", Vector(2)),
        Column("is_active", Boolean, nullable=False),
        Column("deleted_at", DateTime(timezone=True)),
    )

    class_registry = registry()

    class VectorItem:
        pass

    class_registry.map_imperatively(VectorItem, table)
    with patch.object(settings, "semantic_search_enabled", True):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute.return_value = result

        await vector_service.search_similar_with_scores(
            VectorItem, [0.25, 0.75], limit=4, min_score=0.63
        )

    statement = mock_db.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT")
    where_clause = sql.split("WHERE", maxsplit=1)[1].split("ORDER BY", maxsplit=1)[0]
    assert "vector_items.is_active = true" in where_clause
    assert "vector_items.deleted_at IS NULL" in where_clause
    assert "ORDER BY similarity_score DESC" in sql

    def placeholder_for(value: float | int) -> str:
        name = next(
            (name for name, bound in compiled.params.items() if bound == value), None
        )
        assert name is not None, f"expected SQL bind value {value!r}"
        return f"%({name})s"

    assert f">= {placeholder_for(0.63)}" in where_clause
    assert f"> {placeholder_for(-math.inf)}" in where_clause
    assert f"< {placeholder_for(math.inf)}" in where_clause
    assert placeholder_for(4) in sql.split("LIMIT", maxsplit=1)[1]
