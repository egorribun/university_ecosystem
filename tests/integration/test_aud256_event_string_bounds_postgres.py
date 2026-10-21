"""Check migrated Event columns and bounded PostgreSQL VARCHAR behavior."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL event string coverage",
    ),
]

_EVENT_VARCHAR_FIELDS = (
    ("title", 512),
    ("title_en", 512),
    ("location", 512),
    ("location_en", 512),
    ("event_type", 128),
    ("event_type_en", 128),
    ("speaker", 512),
    ("image_url", 2048),
)


def _assert_postgresql(db_session: AsyncSession) -> None:
    assert db_session.get_bind().dialect.name == "postgresql"


async def _bounded_probe_table(
    db_session: AsyncSession, field: str, limit: int
) -> Table:
    orm_type = Event.__table__.c[field].type
    assert getattr(orm_type, "length", None) == limit
    table = Table(
        f"aud256_event_probe_{uuid4().hex}",
        MetaData(),
        Column("probe_id", Integer, primary_key=True),
        Column("value", orm_type, nullable=False),
        prefixes=["TEMPORARY"],
    )
    await db_session.run_sync(
        lambda session: table.create(session.connection(), checkfirst=False)
    )
    return table


async def _probe_readback(
    db_session: AsyncSession, table: Table, probe_id: int, value: str
) -> str:
    await db_session.execute(insert(table).values(probe_id=probe_id, value=value))
    result = await db_session.execute(
        select(table.c.value).where(table.c.probe_id == probe_id)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_migrated_event_columns_are_unbounded_varchar(
    db_session: AsyncSession,
) -> None:
    _assert_postgresql(db_session)
    result = await db_session.execute(
        text(
            """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'events'
              AND column_name IN (
                  'title', 'title_en', 'location', 'location_en',
                  'event_type', 'event_type_en', 'speaker', 'image_url'
              )
            """
        )
    )
    actual = {
        row["column_name"]: (row["data_type"], row["character_maximum_length"])
        for row in result.mappings()
    }
    expected = {
        field: ("character varying", None) for field, _ in _EVENT_VARCHAR_FIELDS
    }
    assert actual == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
async def test_migrated_event_column_round_trips_values_over_model_bound(
    db_session: AsyncSession, field: str, limit: int
) -> None:
    _assert_postgresql(db_session)
    for value in ("x" * (limit + 1), "x" * limit + " ", "Я" * (limit + 1)):
        record = Event(
            title="AUD-256 migrated-column probe",
            starts_at=datetime(2035, 1, 1, 10, tzinfo=UTC),
            ends_at=datetime(2035, 1, 1, 11, tzinfo=UTC),
        )
        setattr(record, field, value)
        async with db_session.begin_nested():
            db_session.add(record)
            await db_session.flush()
            await db_session.refresh(record)
            assert getattr(record, field) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
async def test_bounded_model_varchar_truncates_only_excess_ascii_spaces(
    db_session: AsyncSession, field: str, limit: int
) -> None:
    _assert_postgresql(db_session)
    table = await _bounded_probe_table(db_session, field, limit)
    bounded = "x" * (limit - 2) + "  "
    for probe_id, value in enumerate((bounded, bounded + " ", bounded + "   ")):
        assert await _probe_readback(db_session, table, probe_id, value) == bounded


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
async def test_bounded_model_varchar_counts_characters_not_utf8_bytes(
    db_session: AsyncSession, field: str, limit: int
) -> None:
    _assert_postgresql(db_session)
    table = await _bounded_probe_table(db_session, field, limit)
    value = "Я" * limit
    assert len(value.encode("utf-8")) > limit
    assert await _probe_readback(db_session, table, 1, value) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
@pytest.mark.parametrize(
    "excess",
    ["\t", "\n", "\u00a0", "x"],
    ids=["tab", "line-feed", "nbsp", "nonspace"],
)
async def test_bounded_model_varchar_rejects_excess_non_ascii_space(
    db_session: AsyncSession, field: str, limit: int, excess: str
) -> None:
    _assert_postgresql(db_session)
    table = await _bounded_probe_table(db_session, field, limit)
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                insert(table).values(probe_id=1, value="x" * limit + excess)
            )
    original = exc_info.value.orig
    assert getattr(original, "sqlstate", getattr(original, "pgcode", None)) == "22001"
