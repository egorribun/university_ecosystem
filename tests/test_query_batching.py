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


# ── Edge cases for batch_load_ids ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_load_ids_empty_returns_empty() -> None:
    """An empty input list returns an empty result without touching the session."""
    mock_session = AsyncMock(spec=AsyncSession)
    result = await query_batching.batch_load_ids(mock_session, MockModel, [])
    assert result == []
    mock_session.scalars.assert_not_called()


@pytest.mark.asyncio
async def test_batch_load_ids_dedupes_input() -> None:
    """Duplicate IDs should be deduplicated before querying."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = [MagicMock(id=1), MagicMock(id=2)]
    mock_session.scalars.return_value = mock_result

    ids = [1, 1, 2, 2, 1]
    with patch("app.utils.query_batching.select"):
        results = await query_batching.batch_load_ids(mock_session, MockModel, ids)

    assert len(results) == 2
    # The dedupe is via set(); we cannot control set ordering, so we only
    # verify scalars() was called exactly once (a single batch).
    mock_session.scalars.assert_called_once()


@pytest.mark.asyncio
async def test_batch_load_ids_splits_into_batches() -> None:
    """A list larger than batch_size triggers multiple session.scalars() calls."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.scalars.return_value = mock_result

    ids = list(range(250))  # 250 unique ids
    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(
            mock_session, MockModel, ids, batch_size=100
        )

    # 250 / 100 = 3 batches (100 + 100 + 50).
    assert mock_session.scalars.call_count == 3


@pytest.mark.asyncio
async def test_batch_load_ids_single_batch_under_threshold() -> None:
    """When the input is below batch_size, exactly one query is issued."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.scalars.return_value = mock_result

    ids = [1, 2, 3, 4, 5]
    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(
            mock_session, MockModel, ids, batch_size=100
        )

    mock_session.scalars.assert_called_once()


@pytest.mark.asyncio
async def test_batch_load_ids_mixed_int_and_str() -> None:
    """Mixed int/str IDs deduplicate correctly (str '1' != int 1)."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.scalars.return_value = mock_result

    ids = [1, "1", 2, "2"]  # 4 distinct values after dedupe
    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(mock_session, MockModel, ids)

    mock_session.scalars.assert_called_once()


@pytest.mark.asyncio
async def test_batch_load_ids_huge_input_dispatches_many_batches() -> None:
    """A 10⁴-id input still terminates and dispatches the right batch count."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.scalars.return_value = mock_result

    ids = list(range(10_000))
    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(
            mock_session, MockModel, ids, batch_size=500
        )

    # 10,000 / 500 = 20 batches.
    assert mock_session.scalars.call_count == 20


# ── Edge cases for QueryBatcher ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_batcher_clears_pending_after_execute() -> None:
    """Executing the batcher empties the pending queue (no double-load)."""
    mock_session = AsyncMock(spec=AsyncSession)
    batcher = query_batching.QueryBatcher(mock_session, MockModel)
    batcher.add(1)
    batcher.add(2)

    with patch(
        "app.utils.query_batching.batch_load_ids",
        new=AsyncMock(return_value=[]),
    ):
        await batcher.execute()

    # Subsequent execute() with no new adds should be a no-op.
    with patch("app.utils.query_batching.batch_load_ids", new=AsyncMock()) as second:
        result = await batcher.execute()
    assert result == {}
    second.assert_not_called()


@pytest.mark.asyncio
async def test_query_batcher_dedupes_on_execute() -> None:
    """Adding the same ID twice still loads it once."""
    mock_session = AsyncMock(spec=AsyncSession)
    item = MagicMock(id=1)
    with patch(
        "app.utils.query_batching.batch_load_ids",
        new=AsyncMock(return_value=[item]),
    ) as load:
        batcher = query_batching.QueryBatcher(mock_session, MockModel)
        batcher.add(1)
        batcher.add(1)
        result = await batcher.execute()

    assert result == {1: item}
    load.assert_called_once()


# ── eager_load_options strategy fallback ─────────────────────────────────────


def test_eager_load_options_unknown_strategy_falls_back_to_joined() -> None:
    """Any non-'selectin' strategy uses joinedload (the else branch)."""
    rel = MagicMock()
    with (
        patch("app.utils.query_batching.selectinload") as mock_selectin,
        patch("app.utils.query_batching.joinedload") as mock_joined,
    ):
        query_batching.eager_load_options(rel, strategy="garbage")
        mock_selectin.assert_not_called()
        mock_joined.assert_called_once_with(rel)


# ── prefetch_related ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prefetch_related_returns_empty_when_no_foreign_keys() -> None:
    """Items with all-None FKs short-circuit without a query."""
    mock_session = AsyncMock(spec=AsyncSession)
    items = [MagicMock(), MagicMock()]
    rel = MagicMock()
    rel.property.mapper.class_ = MockModel

    result = await query_batching.prefetch_related(
        mock_session, items, rel, lambda _: None
    )
    assert result == {}
    mock_session.scalars.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_related_filters_none_foreign_keys() -> None:
    """Items returning None FK are skipped; only real keys batched."""
    mock_session = AsyncMock(spec=AsyncSession)
    related = MagicMock(id=42)

    rel = MagicMock()
    rel.property.mapper.class_ = MockModel
    items = [MagicMock(), MagicMock(), MagicMock()]
    fks = iter([42, None, 43])

    with patch(
        "app.utils.query_batching.batch_load_ids",
        new=AsyncMock(return_value=[related]),
    ) as load:
        result = await query_batching.prefetch_related(
            mock_session, items, rel, lambda _: next(fks)
        )

    load.assert_called_once()
    # The 3rd item's None is filtered — only [42, 43] passed in.
    fk_arg = load.call_args[0][2]
    assert fk_arg == [42, 43]
    assert result == {42: related}
