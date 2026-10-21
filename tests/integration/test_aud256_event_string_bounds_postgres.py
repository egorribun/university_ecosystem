"""Verify event VARCHAR storage semantics against the owned PostgreSQL database."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DataError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL event VARCHAR coverage",
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


def _event_with_value(field: str, value: str) -> Event:
    record = Event(
        title="AUD-256 storage regression",
        starts_at=datetime(2035, 1, 1, 10, tzinfo=UTC),
        ends_at=datetime(2035, 1, 1, 11, tzinfo=UTC),
    )
    setattr(record, field, value)
    return record


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
async def test_event_varchar_truncates_only_excess_ascii_spaces(
    db_session: AsyncSession, field: str, limit: int
) -> None:
    assert db_session.get_bind().dialect.name == "postgresql"
    bounded = "x" * (limit - 2) + "  "
    for value in (bounded, bounded + " ", bounded + "   "):
        record = _event_with_value(field, value)
        async with db_session.begin_nested():
            db_session.add(record)
            await db_session.flush()
            await db_session.refresh(record)
            assert getattr(record, field) == bounded


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
async def test_event_varchar_counts_characters_not_utf8_bytes(
    db_session: AsyncSession, field: str, limit: int
) -> None:
    assert db_session.get_bind().dialect.name == "postgresql"
    value = "Я" * limit
    assert len(value.encode("utf-8")) > limit
    record = _event_with_value(field, value)
    async with db_session.begin_nested():
        db_session.add(record)
        await db_session.flush()
        await db_session.refresh(record)
        assert getattr(record, field) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), _EVENT_VARCHAR_FIELDS)
@pytest.mark.parametrize(
    "excess",
    ["\t", "\n", "\u00a0", "x"],
    ids=["tab", "line-feed", "nbsp", "nonspace"],
)
async def test_event_varchar_rejects_excess_non_ascii_space(
    db_session: AsyncSession, field: str, limit: int, excess: str
) -> None:
    assert db_session.get_bind().dialect.name == "postgresql"
    record = _event_with_value(field, "x" * limit + excess)
    with pytest.raises(DataError) as exc_info:
        async with db_session.begin_nested():
            db_session.add(record)
            await db_session.flush()
    original = exc_info.value.orig
    assert getattr(original, "sqlstate", getattr(original, "pgcode", None)) == "22001"
