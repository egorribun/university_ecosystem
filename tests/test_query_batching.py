from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import query_batching


# MockModel doesn't need to be complex if we mock select()
class MockModel:
    id = MagicMock()


MockModel.id.key = "id"


@pytest.mark.asyncio
async def test_batch_load_ids():
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    # Mock result.all() returning list
    mock_result.all.return_value = [MagicMock(id=1), MagicMock(id=2)]
    mock_session.scalars.return_value = mock_result

    ids = [1, 2, 1]

    # We must patch select in query_batching to avoid
    # SQLAlchemy strict checks on MockModel
    with patch("app.utils.query_batching.select") as mock_select:
        results = await query_batching.batch_load_ids(mock_session, MockModel, ids)

        assert len(results) == 2
        mock_select.assert_called_once()
        mock_session.scalars.assert_called_once()


@pytest.mark.asyncio
async def test_query_batcher():
    mock_session = AsyncMock(spec=AsyncSession)
    item1 = MagicMock(id=1)
    item2 = MagicMock(id=2)

    # Patch batch_load_ids to return our items
    with patch("app.utils.query_batching.batch_load_ids", new=AsyncMock()) as mock_load:
        mock_load.return_value = [item1, item2]

        batcher = query_batching.QueryBatcher(mock_session, MockModel)
        batcher.add(1)
        batcher.add(2)

        results = await batcher.execute()

        assert results[1] == item1
        assert results[2] == item2
        mock_load.assert_called_once()
        # Verify ids arg is passed correctly
        call_args = mock_load.call_args
        assert call_args[0][2] == [1, 2]  # ids argument position


@pytest.mark.asyncio
async def test_query_batcher_empty():
    mock_session = AsyncMock()
    batcher = query_batching.QueryBatcher(mock_session, MockModel)
    results = await batcher.execute()
    assert results == {}


def test_eager_load_options():
    rel = MagicMock()
    # Mock selectinload and joinedload
    with (
        patch("app.utils.query_batching.selectinload") as mock_selectin,
        patch("app.utils.query_batching.joinedload") as mock_joined,
    ):
        opts = query_batching.eager_load_options(rel, strategy="selectin")
        assert len(opts) == 1
        mock_selectin.assert_called_once_with(rel)

        opts_joined = query_batching.eager_load_options(rel, strategy="joined")
        assert len(opts_joined) == 1
        mock_joined.assert_called_once_with(rel)


def test_apply_eager_loading():
    stmt = MagicMock()
    rel = MagicMock()
    with patch("app.utils.query_batching.eager_load_options") as mock_opts:
        mock_opts.return_value = ["opt1"]
        res = query_batching.apply_eager_loading(stmt, rel, strategy="selectin")

        stmt.options.assert_called_once_with("opt1")
        assert res == stmt.options.return_value
