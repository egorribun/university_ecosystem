"""Execute pagination SQL against deterministic PostgreSQL-expression stand-ins.

SQLite UDFs supply precomputed relevance/distance; real SQL performs filtering,
ordering and LIMIT. This tests continuation, not PostgreSQL FTS/vector scoring.
"""

import math
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles, deregister
from sqlalchemy.sql.elements import BinaryExpression

from app.core.config import settings
from app.models import Event, News
from app.repositories.unit_of_work import uow_from_session
from app.services.event_service import EventService
from app.services.news_service import NewsService
from app.utils.pagination import encode_datetime_cursor


@pytest.fixture
async def ranked_database(db_session):
    def compile_binary(element, compiler, **kwargs):
        operator = getattr(element.operator, "opstring", None)
        if operator in {"@@", "<=>"}:
            function = "fts_match" if operator == "@@" else "vector_distance"
            return f"{function}({compiler.process(element.left, **kwargs)}, {compiler.process(element.right, **kwargs)})"
        return compiler.visit_binary(element, **kwargs)

    compiles(BinaryExpression, "sqlite")(compile_binary)
    connection = await db_session.connection()

    def install(driver, _record=None):
        driver.create_function("plainto_tsquery", 2, lambda _language, query: query)
        driver.create_function("ts_rank", 2, lambda score, _query: float(score or 0))
        driver.create_function("fts_match", 2, lambda _document, _query: 1)
        driver.create_function(
            "vector_distance",
            2,
            lambda distance, _query: float(distance) if distance is not None else None,
        )

    await connection.run_sync(lambda conn: install(conn.connection.dbapi_connection))
    engine = db_session.bind.sync_engine
    event.listen(engine, "connect", install)
    try:
        yield db_session
    finally:
        event.remove(engine, "connect", install)
        deregister(BinaryExpression)


async def _seed(db, user, kind):
    now = datetime.now(UTC)
    dates = [now + timedelta(days=i) for i in [3, 3, 2, 4, 1, 1]]
    scores = (
        ["3", "3", "2", "1", "0", "0"]
        if kind == "event"
        else ["0.1", "0.1", "0.2", "0.3", None, None]
    )
    records = []
    for position, (date, score) in enumerate(zip(dates, scores, strict=True), 1):
        if kind == "event":
            row = Event(
                id=UUID(int=(0xA << 124) + position),
                title=f"Result {position}",
                search_vector=score,
                starts_at=date,
                ends_at=date + timedelta(hours=1),
                created_by=user.id,
            )
        else:
            row = News(
                id=UUID(int=(0xA << 124) + position),
                title=f"Result {position}",
                content="Content",
                created_at=date,
                embedding=score,
            )
        db.add(row)
        records.append(row)
    await db.commit()
    return records


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
@pytest.mark.parametrize("delete_anchor", [False, True])
async def test_ranked_pages_cover_every_result_once(
    ranked_database, user_factory, monkeypatch, kind, delete_anchor
):
    user = await user_factory()
    records = await _seed(ranked_database, user, kind)
    monkeypatch.setattr(settings, "semantic_search_enabled", kind == "news")
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    uow = uow_from_session(ranked_database)
    service = EventService(uow, vector) if kind == "event" else NewsService(uow, vector)
    fetch = service.get_events if kind == "event" else service.list_news
    ids = []
    cursor = None
    for page_index in range(7):
        page = await fetch(search="query", limit=1, cursor=cursor)
        ids.extend(item.id for item in page.items)
        if page_index == 0 and delete_anchor:
            await ranked_database.execute(
                delete(Event if kind == "event" else News).where(
                    (Event if kind == "event" else News).id == page.items[0].id
                )
            )
            await ranked_database.commit()
        if not page.has_more:
            break
        assert page.next_cursor != cursor
        cursor = page.next_cursor
    expected = [row.id for row in records]
    if kind == "news":
        expected[:2] = reversed(expected[:2])  # descending UUID tie-breaker
        expected[-2:] = reversed(expected[-2:])
    assert ids == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_legacy_datetime_cursor_resolves_relevance_anchor(
    ranked_database, user_factory, monkeypatch, kind
):
    user = await user_factory()
    records = await _seed(ranked_database, user, kind)
    monkeypatch.setattr(settings, "semantic_search_enabled", kind == "news")
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    uow = uow_from_session(ranked_database)
    service = EventService(uow, vector) if kind == "event" else NewsService(uow, vector)
    fetch = service.get_events if kind == "event" else service.list_news
    anchor = records[0] if kind == "event" else records[1]
    cursor = encode_datetime_cursor(
        anchor.starts_at if kind == "event" else anchor.created_at, str(anchor.id)
    )
    page = await fetch(search="query", limit=10, cursor=cursor)
    expected = (
        [row.id for row in records[1:]]
        if kind == "event"
        else [records[0].id, records[2].id, records[3].id, records[5].id, records[4].id]
    )
    assert [item.id for item in page.items] == expected


@pytest.mark.asyncio
async def test_legacy_event_cursor_uses_the_matching_unique_rank_anchor(
    ranked_database, user_factory, monkeypatch
):
    user = await user_factory()
    records = await _seed(ranked_database, user, "event")
    monkeypatch.setattr(settings, "semantic_search_enabled", False)
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    service = EventService(uow_from_session(ranked_database), vector)
    anchor = records[2]
    cursor = encode_datetime_cursor(anchor.starts_at, str(anchor.id))

    page = await service.get_events(search="query", limit=10, cursor=cursor)

    assert [item.id for item in page.items] == [
        records[3].id,
        records[4].id,
        records[5].id,
    ]


@pytest.mark.asyncio
async def test_event_hybrid_rank_prefers_the_closer_embedding(
    ranked_database, user_factory, monkeypatch
):
    user = await user_factory()
    now = datetime.now(UTC)
    closer = Event(
        id=UUID(int=(0xB << 124) + 1),
        title="Equal text rank",
        search_vector="1",
        embedding="0.1",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=3),
        created_by=user.id,
    )
    farther = Event(
        id=UUID(int=(0xB << 124) + 2),
        title="Equal text rank",
        search_vector="1",
        embedding="0.8",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
        created_by=user.id,
    )
    ranked_database.add_all([closer, farther])
    await ranked_database.commit()

    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    service = EventService(uow_from_session(ranked_database), vector)

    page = await service.get_events(search="query", limit=10)

    assert [item.id for item in page.items] == [closer.id, farther.id]


def test_ranked_cursor_round_trip_preserves_nulls_and_precision():
    from app.utils.pagination import (
        decode_ranked_datetime_cursor,
        encode_ranked_datetime_cursor,
    )

    moment = datetime(2026, 10, 2, 12, 3, 4, 567891, tzinfo=UTC)
    for score in (None, 0.0, 1.23456789012345):
        cursor = encode_ranked_datetime_cursor(moment, str(UUID(int=42)), score)
        assert decode_ranked_datetime_cursor(cursor) == (
            moment,
            str(UUID(int=42)),
            score,
        )


@pytest.mark.parametrize(
    "cursor",
    [
        None,
        "",
        "legacy",
        "r1:",
        "r1:wrong:bad",
        "r1:nan:1:id",
        "r1:inf:1:id",
        "r1:1.0:bad:id",
    ],
)
def test_ranked_cursor_rejects_invalid_values(cursor):
    from app.utils.pagination import decode_ranked_datetime_cursor

    assert decode_ranked_datetime_cursor(cursor) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_missing_legacy_anchor_has_no_next_page(
    ranked_database, monkeypatch, kind
):
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    uow = uow_from_session(ranked_database)
    service = EventService(uow, vector) if kind == "event" else NewsService(uow, vector)
    fetch = service.get_events if kind == "event" else service.list_news
    cursor = encode_datetime_cursor(datetime.now(UTC), str(UUID(int=42)))
    result = await fetch(search="query", cursor=cursor)
    assert result.items == []
    assert not result.has_more


@pytest.mark.asyncio
async def test_hybrid_rank_retains_full_text_rows_without_embeddings(
    ranked_database, user_factory, monkeypatch
):
    user = await user_factory()
    records = await _seed(ranked_database, user, "event")
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    service = EventService(uow_from_session(ranked_database), vector)
    first = await service.get_events(search="query", limit=2)
    second = await service.get_events(
        search="query", limit=10, cursor=first.next_cursor
    )
    assert [item.id for item in first.items + second.items] == [
        row.id for row in records
    ]


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_ranked_cursor_never_encodes_nonfinite_score(score):
    from app.utils.pagination import encode_ranked_datetime_cursor

    with pytest.raises(ValueError, match="finite"):
        encode_ranked_datetime_cursor(datetime.now(UTC), str(UUID(int=42)), score)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["event", "news"])
async def test_native_query_binds_pgvector_nan_as_postgresql_float(monkeypatch, kind):
    from unittest.mock import MagicMock

    from app.repositories.event_repository import EventRepository
    from app.repositories.news_repository import NewsRepository

    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result
    repo = EventRepository(db) if kind == "event" else NewsRepository(db)
    fetch = repo.search_events if kind == "event" else repo.list_news
    await fetch(search_query="query", query_embedding=[1.0] * 1536)
    statement = db.execute.call_args.args[0]
    from sqlalchemy.dialects.postgresql import asyncpg

    # SQLite collapses NaN and None to NULL; this checks the PostgreSQL wire binding.
    compiled = statement.compile(dialect=asyncpg.dialect())
    normalization = re.search(r"nullif\([^,]+, \$(\d+)::FLOAT\)", str(compiled))
    assert normalization is not None, str(compiled)
    parameter_name = compiled.positiontup[int(normalization.group(1)) - 1]
    assert math.isnan(compiled.params[parameter_name])


@pytest.mark.asyncio
async def test_ranked_news_cursor_uses_same_order_for_tied_scores(
    ranked_database: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    older = News(
        id=UUID(int=(0xA << 124) + 2),
        title="Older tied result",
        content="Content",
        created_at=now - timedelta(days=2),
        embedding="0.1",
    )
    newer = News(
        id=UUID(int=(0xA << 124) + 1),
        title="Newer tied result",
        content="Content",
        created_at=now - timedelta(days=1),
        embedding="0.1",
    )
    ranked_database.add_all([older, newer])
    await ranked_database.commit()
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    vector = AsyncMock()
    vector.get_embedding.return_value = [1.0, 0.0]
    service = NewsService(uow_from_session(ranked_database), vector)

    ids = []
    cursor = None
    for _ in range(3):
        page = await service.list_news(search="query", limit=1, cursor=cursor)
        ids.extend(item.id for item in page.items)
        if not page.has_more:
            break
        assert page.next_cursor != cursor
        cursor = page.next_cursor

    assert ids == [newer.id, older.id]
