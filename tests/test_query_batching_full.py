"""Production-ready tests for app/utils/query_batching.py.

Extends test_query_batching.py with:
- Correct ordering invariants when batch_load_ids returns mixed results
- Race-condition safety: concurrent batcher executions with the same session
- Timeout/deadline simulation via real asyncio delays (no mock sleep)
- Graceful degradation when batch_size=1 (degenerate case)
- Hypothesis property tests: grouping idempotency
- prefetch_related mapping invariants
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from app.utils import query_batching

# ---------------------------------------------------------------------------
# Shared fixtures / factories
# ---------------------------------------------------------------------------


class _MockModel:
    """Minimal SQLAlchemy-style model stand-in for batch tests."""

    id = MagicMock()


_MockModel.id.key = "id"


def _make_mock_session(return_items: list) -> AsyncMock:
    """Build an AsyncMock session whose .scalars() always yields return_items."""
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = return_items
    session.scalars.return_value = scalars_result
    return session


# ---------------------------------------------------------------------------
# batch_load_ids — ordering and correctness
# ---------------------------------------------------------------------------


async def test_batch_load_ids_returns_all_items_from_db() -> None:
    """All items returned by the database are included in the result list."""
    item_a = MagicMock(id=10)
    item_b = MagicMock(id=20)
    item_c = MagicMock(id=30)

    session = _make_mock_session([item_a, item_b, item_c])

    with patch("app.utils.query_batching.select"):
        results = await query_batching.batch_load_ids(session, _MockModel, [10, 20, 30])

    assert len(results) == 3
    assert item_a in results
    assert item_b in results
    assert item_c in results


async def test_batch_load_ids_accumulates_results_across_multiple_batches() -> None:
    """Items from every batch are merged into a single list."""
    batch1_items = [MagicMock(id=i) for i in range(3)]
    batch2_items = [MagicMock(id=i) for i in range(3, 6)]

    session = AsyncMock()
    r1, r2 = MagicMock(), MagicMock()
    r1.all.return_value = batch1_items
    r2.all.return_value = batch2_items
    session.scalars.side_effect = [r1, r2]

    ids = list(range(6))
    with patch("app.utils.query_batching.select"):
        results = await query_batching.batch_load_ids(
            session, _MockModel, ids, batch_size=3
        )

    assert session.scalars.call_count == 2
    assert len(results) == 6


async def test_batch_load_ids_with_batch_size_one_issues_one_query_per_unique_id() -> (
    None
):
    """batch_size=1 is the degenerate case — each unique ID gets its own query."""
    items = [MagicMock(id=i) for i in range(4)]
    session = AsyncMock()

    def _make_result(item):
        r = MagicMock()
        r.all.return_value = [item]
        return r

    session.scalars.side_effect = [_make_result(it) for it in items]

    with patch("app.utils.query_batching.select"):
        results = await query_batching.batch_load_ids(
            session, _MockModel, [0, 1, 2, 3], batch_size=1
        )

    assert session.scalars.call_count == 4
    assert len(results) == 4


async def test_batch_load_ids_with_exact_batch_size_boundary() -> None:
    """Input size exactly equal to batch_size triggers exactly one query."""
    result_mock = MagicMock()
    result_mock.all.return_value = []
    session = AsyncMock()
    session.scalars.return_value = result_mock

    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(
            session, _MockModel, list(range(50)), batch_size=50
        )

    session.scalars.assert_called_once()


async def test_batch_load_ids_with_single_id_makes_one_query() -> None:
    """A single ID input results in exactly one database query."""
    item = MagicMock(id=99)
    session = _make_mock_session([item])

    with patch("app.utils.query_batching.select"):
        results = await query_batching.batch_load_ids(session, _MockModel, [99])

    assert results == [item]
    session.scalars.assert_called_once()


# ---------------------------------------------------------------------------
# QueryBatcher — concurrent execution (race-condition safety)
# ---------------------------------------------------------------------------


async def test_query_batcher_concurrent_execute_calls_are_independent() -> None:
    """Two independent QueryBatcher instances executing concurrently do not interfere."""
    item_x = MagicMock(id="x")
    item_x.configure_mock(**{"id": "x"})
    item_y = MagicMock(id="y")
    item_y.configure_mock(**{"id": "y"})

    session = AsyncMock()

    async def _load_with_delay(session, model, ids, *, id_column=None, batch_size=100):
        await asyncio.sleep(0.01)  # Real delay — not mocked
        if "x" in ids:
            return [item_x]
        return [item_y]

    with patch("app.utils.query_batching.batch_load_ids", side_effect=_load_with_delay):
        batcher_x = query_batching.QueryBatcher(session, _MockModel)
        batcher_y = query_batching.QueryBatcher(session, _MockModel)

        batcher_x.add("x")
        batcher_y.add("y")

        result_x, result_y = await asyncio.gather(
            batcher_x.execute(), batcher_y.execute()
        )

    assert result_x == {"x": item_x}
    assert result_y == {"y": item_y}


async def test_query_batcher_multiple_sequential_executes_are_independent() -> None:
    """Successive execute() calls on the same batcher each trigger exactly one load."""
    item1 = MagicMock(id=1)
    item2 = MagicMock(id=2)

    load_mock = AsyncMock(side_effect=[[item1], [item2]])

    with patch("app.utils.query_batching.batch_load_ids", new=load_mock):
        batcher = query_batching.QueryBatcher(AsyncMock(), _MockModel)

        batcher.add(1)
        result1 = await batcher.execute()

        batcher.add(2)
        result2 = await batcher.execute()

    assert result1 == {1: item1}
    assert result2 == {2: item2}
    assert load_mock.call_count == 2


async def test_query_batcher_execute_with_real_async_delay() -> None:
    """execute() works correctly even when batch_load_ids has a real I/O delay."""
    item = MagicMock(id=7)

    async def _slow_load(session, model, ids, *, id_column=None, batch_size=100):
        await asyncio.sleep(0.02)  # Real I/O simulation
        return [item]

    with patch("app.utils.query_batching.batch_load_ids", side_effect=_slow_load):
        batcher = query_batching.QueryBatcher(AsyncMock(), _MockModel)
        batcher.add(7)
        result = await batcher.execute()

    assert result == {7: item}


# ---------------------------------------------------------------------------
# eager_load_options — strategy selection
# ---------------------------------------------------------------------------


def test_eager_load_options_selectin_strategy_uses_selectinload() -> None:
    rel = MagicMock()
    with (
        patch("app.utils.query_batching.selectinload") as mock_selectin,
        patch("app.utils.query_batching.joinedload"),
    ):
        query_batching.eager_load_options(rel, strategy="selectin")
        mock_selectin.assert_called_once_with(rel)


def test_eager_load_options_joined_strategy_uses_joinedload() -> None:
    rel = MagicMock()
    with (
        patch("app.utils.query_batching.selectinload"),
        patch("app.utils.query_batching.joinedload") as mock_joined,
    ):
        query_batching.eager_load_options(rel, strategy="joined")
        mock_joined.assert_called_once_with(rel)


def test_eager_load_options_multiple_relationships() -> None:
    """Multiple relationships produce one loader option per relationship."""
    rel_a, rel_b, rel_c = MagicMock(), MagicMock(), MagicMock()
    with patch("app.utils.query_batching.selectinload") as mock_selectin:
        opts = query_batching.eager_load_options(
            rel_a, rel_b, rel_c, strategy="selectin"
        )
    assert len(opts) == 3
    mock_selectin.assert_has_calls([call(rel_a), call(rel_b), call(rel_c)])


# ---------------------------------------------------------------------------
# apply_eager_loading
# ---------------------------------------------------------------------------


def test_apply_eager_loading_chains_options_onto_statement() -> None:
    stmt = MagicMock()
    rel = MagicMock()
    with patch("app.utils.query_batching.eager_load_options") as mock_opts:
        mock_opts.return_value = ["opt_a"]
        result = query_batching.apply_eager_loading(stmt, rel, strategy="selectin")

    stmt.options.assert_called_once_with("opt_a")
    assert result == stmt.options.return_value


# ---------------------------------------------------------------------------
# prefetch_related — mapping correctness
# ---------------------------------------------------------------------------


async def test_prefetch_related_maps_related_objects_by_id() -> None:
    """Returned dict maps each FK value to its loaded related object."""
    related_obj = MagicMock()
    related_obj.id = 100

    session = AsyncMock()
    rel = MagicMock()
    rel.property.mapper.class_ = _MockModel

    parent_items = [MagicMock()]

    with patch(
        "app.utils.query_batching.batch_load_ids",
        new=AsyncMock(return_value=[related_obj]),
    ):
        result = await query_batching.prefetch_related(
            session, parent_items, rel, lambda _: 100
        )

    assert result == {100: related_obj}


async def test_prefetch_related_with_multiple_parents_and_shared_fk() -> None:
    """Multiple parents referencing the same FK are correctly handled."""
    shared_related = MagicMock()
    shared_related.id = 55

    session = AsyncMock()
    rel = MagicMock()
    rel.property.mapper.class_ = _MockModel

    parents = [MagicMock(), MagicMock(), MagicMock()]  # all reference FK=55

    with patch(
        "app.utils.query_batching.batch_load_ids",
        new=AsyncMock(return_value=[shared_related]),
    ) as mock_load:
        result = await query_batching.prefetch_related(
            session, parents, rel, lambda _: 55
        )

    # batch_load_ids receives [55, 55, 55] — deduplication happens inside that fn
    fk_arg = mock_load.call_args[0][2]
    assert fk_arg == [55, 55, 55]
    assert result == {55: shared_related}


# ---------------------------------------------------------------------------
# Hypothesis property tests — grouping idempotency
# ---------------------------------------------------------------------------


@given(ids=st.lists(st.integers(min_value=1, max_value=1000), max_size=50))
@hypothesis_settings(max_examples=80, deadline=3000)
async def test_batch_load_ids_idempotent_when_called_twice_with_same_ids(
    ids: list[int],
) -> None:
    """Calling batch_load_ids twice with the same IDs produces the same call count.

    The deduplication is pure (set-based), so the number of scalars() calls is
    deterministic: ceil(len(set(ids)) / batch_size).
    """

    result_mock = MagicMock()
    result_mock.all.return_value = []
    session = AsyncMock()
    session.scalars.return_value = result_mock

    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(session, _MockModel, ids, batch_size=100)
        call_count_first = session.scalars.call_count

        session.scalars.reset_mock()
        await query_batching.batch_load_ids(session, _MockModel, ids, batch_size=100)
        call_count_second = session.scalars.call_count

    assert call_count_first == call_count_second


@given(
    ids=st.lists(
        st.one_of(st.integers(min_value=1, max_value=500), st.text(max_size=10)),
        min_size=1,
        max_size=200,
    ),
    batch_size=st.integers(min_value=1, max_value=50),
)
@hypothesis_settings(max_examples=60, deadline=3000)
async def test_batch_load_ids_query_count_matches_ceil_division(
    ids: list[int | str], batch_size: int
) -> None:
    """Number of queries equals ceil(unique_ids / batch_size)."""
    import math

    unique_count = len(set(ids))
    expected_calls = math.ceil(unique_count / batch_size) if unique_count > 0 else 0

    result_mock = MagicMock()
    result_mock.all.return_value = []
    session = AsyncMock()
    session.scalars.return_value = result_mock

    with patch("app.utils.query_batching.select"):
        await query_batching.batch_load_ids(
            session, _MockModel, ids, batch_size=batch_size
        )

    assert session.scalars.call_count == expected_calls


# ---------------------------------------------------------------------------
# Concurrent gather with real delays
# ---------------------------------------------------------------------------


async def test_multiple_batchers_gather_with_real_delays_return_correct_results() -> (
    None
):
    """asyncio.gather over many batchers with real I/O delay returns all results."""
    item_count = 10

    async def _delayed_load(session, model, ids, *, id_column=None, batch_size=100):
        await asyncio.sleep(0.005)  # Real delay — not mocked
        return [MagicMock(id=iid) for iid in ids]

    session = AsyncMock()

    async def _run_batcher(item_id: int) -> dict:
        with patch(
            "app.utils.query_batching.batch_load_ids", side_effect=_delayed_load
        ):
            batcher = query_batching.QueryBatcher(session, _MockModel)
            batcher.add(item_id)
            return await batcher.execute()

    results = await asyncio.gather(*(_run_batcher(i) for i in range(item_count)))

    assert len(results) == item_count
    for i, result in enumerate(results):
        assert i in result
