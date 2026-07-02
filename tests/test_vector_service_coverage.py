from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.vector_service import VectorService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def vector_service(mock_db):
    service = VectorService(mock_db)
    return service


@pytest.mark.asyncio
async def test_get_embedding_disabled(vector_service):
    with patch.object(settings, "semantic_search_enabled", False):
        embedding = await vector_service.get_embedding("test")
        assert len(embedding) == settings.embedding_dimensions
        assert all(x == 0.0 for x in embedding)


@pytest.mark.asyncio
async def test_get_embedding_no_api_key(vector_service):
    # Ensure enabled but no key
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", None),
    ):
        embedding = await vector_service.get_embedding("test")
        assert len(embedding) == settings.embedding_dimensions
        assert all(x == 0.0 for x in embedding)


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
async def test_get_embedding_failure(vector_service):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch.object(settings, "embedding_api_key", "fake-key"),
    ):
        vector_service._client.post = AsyncMock(
            side_effect=ConnectionError("API Error")
        )

        embedding = await vector_service.get_embedding("test")
        assert len(embedding) == settings.embedding_dimensions
        assert all(x == 0.0 for x in embedding)


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

        # Setup operation mocks — label() must return a MagicMock that supports
        # comparison operators (__ge__) because the result is used in
        # `where(score >= min_score)`.
        mock_score_column = MagicMock()
        mock_score_column.desc.return_value = mock_score_column
        # SQLAlchemy column-like: __ge__ should return a clause element, not raise
        mock_score_column.__ge__ = MagicMock(return_value=MagicMock())

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
    with patch("app.services.vector_service.validate_url_not_internal"):
        async with VectorService(mock_db) as service:
            service._client.aclose = AsyncMock()
            assert service.db is mock_db
        service._client.aclose.assert_called_once()
