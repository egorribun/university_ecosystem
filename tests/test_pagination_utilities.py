"""Behavioral tests for app/utils/pagination.py.

Covers encode_cursor, decode_cursor, encode_datetime_cursor,
decode_datetime_cursor, paginate_cursor, CursorPage, CursorParams.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.utils.pagination import (
    CursorPage,
    CursorParams,
    decode_cursor,
    decode_datetime_cursor,
    encode_cursor,
    encode_datetime_cursor,
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


def test_decode_datetime_cursor_rejects_empty_secondary_id():
    """A cursor without its tie-breaker must not reach repository UUID casting."""
    assert decode_datetime_cursor("0:") is None


def test_decode_datetime_cursor_accepts_epoch_with_valid_secondary_id():
    cursor = f"0:{uuid.UUID(int=1)}"

    result = decode_datetime_cursor(cursor)

    assert result == (datetime(1970, 1, 1, tzinfo=UTC), str(uuid.UUID(int=1)))


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
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CursorParams(limit=0)

    with pytest.raises(ValidationError):
        CursorParams(limit=101)


# ---------------------------------------------------------------------------
# CursorPage
# ---------------------------------------------------------------------------


def test_cursor_page_basic():
    page: CursorPage[int] = CursorPage(
        items=[1, 2, 3], next_cursor="abc", has_more=True
    )
    assert len(page.items) == 3
    assert page.has_more


def test_cursor_page_no_more():
    page: CursorPage[str] = CursorPage(
        items=["a"], next_cursor=None, has_more=False, total_count=1
    )
    assert not page.has_more
    assert page.total_count == 1


# ---------------------------------------------------------------------------
# paginate_cursor
# ---------------------------------------------------------------------------
