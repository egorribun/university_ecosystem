import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import column, select

from app.repositories.pagination import (
    CursorParams,
    Page,
    apply_cursor,
    decode_cursor_as_int,
    decode_cursor_as_uuid,
    encode_cursor,
)


def test_encode_decode_uuid():
    u = uuid.uuid4()
    encoded = encode_cursor(u)
    assert isinstance(encoded, str)
    decoded = decode_cursor_as_uuid(encoded)
    assert decoded == u


def test_encode_decode_int():
    val = 12345
    encoded = encode_cursor(val)
    decoded = decode_cursor_as_int(encoded)
    assert decoded == val


def test_decode_invalid():
    with pytest.raises(ValueError):
        decode_cursor_as_uuid("not-base64-!")
    with pytest.raises(ValueError):
        decode_cursor_as_uuid(encode_cursor("not-a-uuid"))
    with pytest.raises(ValueError):
        decode_cursor_as_int(encode_cursor("not-an-int"))


def test_decode_int_rejects_values_outside_uuid_sized_range():
    with pytest.raises(ValueError, match="valid range"):
        decode_cursor_as_int(encode_cursor(-1))
    with pytest.raises(ValueError, match="valid range"):
        decode_cursor_as_int(encode_cursor(2**128 + 1))


def test_cursor_params_properties():
    u = uuid.uuid4()
    encoded = encode_cursor(u)
    params = CursorParams(after=encoded, limit=10)
    assert params.after_uuid == u

    val = 999
    encoded_int = encode_cursor(val)
    params_int = CursorParams(after=encoded_int)
    assert params_int.after_int == val

    # RZ-14: Must pass after=None explicitly because default in dataclass
    # might be the Query object if imported from FastAPI deps.
    params_none = CursorParams(after=None)
    assert params_none.after_uuid is None
    assert params_none.after_int is None


def test_page_from_rows_has_more():
    class Row:
        def __init__(self, id_val):
            self.id = id_val

    rows = [Row(1), Row(2), Row(3)]
    limit = 2
    page = Page.from_rows(rows, limit)
    assert len(page.items) == 2
    assert page.has_more is True
    assert page.next_cursor == encode_cursor(2)


def test_page_from_rows_no_more():
    class Row:
        def __init__(self, id_val):
            self.id = id_val

    rows = [Row(1), Row(2)]
    limit = 2
    page = Page.from_rows(rows, limit)
    assert len(page.items) == 2
    assert page.has_more is False
    assert page.next_cursor is None


def test_page_from_rows_empty():
    page = Page.from_rows([], 10)
    assert len(page.items) == 0
    assert page.has_more is False
    assert page.next_cursor is None


def test_page_empty_factory_and_missing_row_id():
    empty = Page.empty()
    assert empty.items == []
    assert empty.next_cursor is None
    assert empty.has_more is False

    page = Page.from_rows([object(), object()], limit=1)
    assert page.has_more is True
    assert page.next_cursor is None


def test_apply_cursor_limits_without_after_and_decodes_uuid_or_int():
    id_column = column("id")

    first_page = apply_cursor(
        select(id_column), id_column, CursorParams(limit=2, after=None)
    )
    assert first_page._limit_clause.value == 3

    uuid_value = uuid.uuid4()
    uuid_page = apply_cursor(
        select(id_column),
        id_column,
        CursorParams(limit=2, after=encode_cursor(uuid_value)),
    )
    assert "WHERE" in str(uuid_page)

    int_page = apply_cursor(
        select(id_column),
        id_column,
        CursorParams(limit=2, after=encode_cursor(42)),
    )
    assert "WHERE" in str(int_page)


def test_apply_cursor_rejects_malformed_after_value():
    id_column = column("id")

    with pytest.raises(HTTPException) as caught:
        apply_cursor(
            select(id_column),
            id_column,
            CursorParams(limit=2, after=encode_cursor("not-a-cursor")),
        )

    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == "INVALID_CURSOR"
