"""Tests for app/utils/pagination.py

Covers encode_cursor, decode_cursor, encode_datetime_cursor,
decode_datetime_cursor, paginate_cursor, CursorPage, CursorParams.
Goal: 90%+ coverage.
"""
from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.pagination import (
    CursorPage,
    CursorParams,
    decode_cursor,
    decode_datetime_cursor,
    encode_cursor,
    encode_datetime_cursor,
    paginate_cursor,
)


# ---------------------------------------------------------------------------
# encode_cursor / decode_cursor
# ---------------------------------------------------------------------------

def test_encode_cursor_integer():
    encoded = encode_cursor(42)
    decoded = decode_cursor(encoded)
    assert decoded == "42"


def test_encode_cursor_string():
    encoded = encode_cursor("hello-world")
    decoded = decode_cursor(encoded)
    assert decoded == "hello-world"


def test_encode_cursor_uuid():
    value = str(uuid.uuid4())
    encoded = encode_cursor(value)
    decoded = decode_cursor(encoded)
    assert decoded == value


def test_decode_cursor_invalid_returns_empty():
    # Non-base64 string
    result = decode_cursor("not!!valid!!")
    assert result == ""


def test_decode_cursor_empty_string_returns_empty():
    result = decode_cursor("")
    assert result == ""


def test_encode_decode_roundtrip():
    for value in ["abc", "123", "uuid-1234-5678", "0"]:
        assert decode_cursor(encode_cursor(value)) == value


# ---------------------------------------------------------------------------
# encode_datetime_cursor / decode_datetime_cursor
# ---------------------------------------------------------------------------

def test_encode_decode_datetime_cursor_roundtrip():
    now = datetime(2025, 6, 15, 12, 30, 45, 123456, tzinfo=UTC)
    secondary = "abc-123"
    cursor = encode_datetime_cursor(now, secondary)
    result = decode_datetime_cursor(cursor)
    assert result is not None
    decoded_dt, decoded_id = result
    assert decoded_dt == now
    assert decoded_id == secondary


def test_encode_datetime_cursor_naive_datetime():
    """Naive datetime should be treated as UTC."""
    naive = datetime(2025, 1, 1, 0, 0, 0)
    cursor = encode_datetime_cursor(naive, "id-1")
    result = decode_datetime_cursor(cursor)
    assert result is not None
    decoded_dt, _ = result
    assert decoded_dt.tzinfo == UTC


def test_decode_datetime_cursor_none_returns_none():
    assert decode_datetime_cursor(None) is None


def test_decode_datetime_cursor_empty_returns_none():
    assert decode_datetime_cursor("") is None


def test_decode_datetime_cursor_invalid_format_returns_none():
    assert decode_datetime_cursor("not-a-cursor") is None


def test_decode_datetime_cursor_non_integer_timestamp_returns_none():
    assert decode_datetime_cursor("notanumber:secondary") is None


def test_encode_datetime_cursor_int_secondary():
    now = datetime.now(UTC)
    cursor = encode_datetime_cursor(now, 99)
    result = decode_datetime_cursor(cursor)
    assert result is not None
    _, secondary = result
    assert secondary == "99"


# ---------------------------------------------------------------------------
# CursorParams
# ---------------------------------------------------------------------------

def test_cursor_params_defaults():
    params = CursorParams()
    assert params.cursor is None
    assert params.limit == 20


def test_cursor_params_custom():
    params = CursorParams(cursor="abc", limit=50)
    assert params.cursor == "abc"
    assert params.limit == 50


def test_cursor_params_limit_clamps():
    with pytest.raises(Exception):  # pydantic ValidationError
        CursorParams(limit=0)

    with pytest.raises(Exception):
        CursorParams(limit=101)


# ---------------------------------------------------------------------------
# CursorPage
# ---------------------------------------------------------------------------

def test_cursor_page_basic():
    page: CursorPage[int] = CursorPage(items=[1, 2, 3], next_cursor="abc", has_more=True)
    assert len(page.items) == 3
    assert page.has_more


def test_cursor_page_no_more():
    page: CursorPage[str] = CursorPage(items=["a"], next_cursor=None, has_more=False, total_count=1)
    assert not page.has_more
    assert page.total_count == 1


# ---------------------------------------------------------------------------
# paginate_cursor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paginate_cursor_no_cursor_no_total():
    """Basic call without cursor and without total count."""
    session = AsyncMock()
    stmt = MagicMock()
    cursor_column = MagicMock()
    cursor_column.desc.return_value = cursor_column
    cursor_column.key = "id"

    items = [MagicMock() for _ in range(3)]
    for i, item in enumerate(items):
        item.id = i

    # scalars() returns an awaitable that provides .all()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    session.scalars.return_value = mock_scalars

    params = CursorParams(limit=20)
    result = await paginate_cursor(session, stmt, cursor_column, params)

    assert len(result.items) == 3
    assert not result.has_more
    assert result.next_cursor is None
    assert result.total_count is None


@pytest.mark.asyncio
async def test_paginate_cursor_has_more():
    """When there are more items than limit, has_more=True and next_cursor set."""
    session = AsyncMock()
    stmt = MagicMock()
    cursor_column = MagicMock()
    cursor_column.desc.return_value = cursor_column
    cursor_column.key = "created_at"

    # 6 items returned, limit is 5 → has_more
    items = [MagicMock() for _ in range(6)]
    for i, item in enumerate(items):
        item.created_at = f"2025-01-0{i + 1}"

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    session.scalars.return_value = mock_scalars

    params = CursorParams(limit=5)
    result = await paginate_cursor(session, stmt, cursor_column, params)

    assert result.has_more
    assert len(result.items) == 5
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_paginate_cursor_with_total():
    """include_total=True triggers a count query via session.execute."""
    from unittest.mock import patch as mock_patch

    session = AsyncMock()
    stmt = MagicMock()
    cursor_column = MagicMock()
    cursor_column.desc.return_value = cursor_column
    cursor_column.key = "id"

    count_result = MagicMock()
    count_result.scalar.return_value = 42

    items = [MagicMock() for _ in range(2)]
    for i, item in enumerate(items):
        item.id = i

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items

    session.execute.return_value = count_result
    session.scalars.return_value = mock_scalars

    params = CursorParams(limit=10)

    # Patch sqlalchemy.select at the source module since it's locally imported
    mock_select_result = MagicMock()
    mock_select_result.select_from.return_value = mock_select_result

    with mock_patch("sqlalchemy.select", return_value=mock_select_result):
        result = await paginate_cursor(session, stmt, cursor_column, params, include_total=True)

    assert result.total_count == 42




@pytest.mark.asyncio
async def test_paginate_cursor_ascending_order():
    """descending=False should use .asc() ordering."""
    session = AsyncMock()
    stmt = MagicMock()
    cursor_column = MagicMock()
    cursor_column.asc.return_value = cursor_column
    cursor_column.key = "id"

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    session.scalars.return_value = mock_scalars

    params = CursorParams(limit=10)
    result = await paginate_cursor(session, stmt, cursor_column, params, descending=False)

    cursor_column.asc.assert_called()
    assert not result.has_more


@pytest.mark.asyncio
async def test_paginate_cursor_with_cursor_value():
    """When cursor is provided, where clause is applied."""
    session = AsyncMock()
    stmt = MagicMock()
    stmt.where.return_value = stmt
    stmt.order_by.return_value = stmt
    stmt.limit.return_value = stmt
    cursor_column = MagicMock()
    cursor_column.desc.return_value = cursor_column
    cursor_column.key = "id"
    cursor_column.__lt__ = MagicMock(return_value=MagicMock())

    encoded_cursor = encode_cursor("some-value")

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    session.scalars.return_value = mock_scalars

    params = CursorParams(cursor=encoded_cursor, limit=10)
    result = await paginate_cursor(session, stmt, cursor_column, params)

    stmt.where.assert_called()
    assert not result.has_more
