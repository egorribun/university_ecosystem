import datetime

from app.utils.pagination import decode_cursor, decode_datetime_cursor


def test_decode_cursor_exceptions():
    assert decode_cursor("not-base64-!") == ""
    assert decode_cursor("//8=") == ""


def test_decode_datetime_cursor_exceptions():
    assert decode_datetime_cursor(None) is None
    assert decode_datetime_cursor("") is None
    assert decode_datetime_cursor("no_colon") is None
    assert decode_datetime_cursor("notanint:id") is None
    assert decode_datetime_cursor("1234567890:id:extra") == (
        datetime.datetime(1970, 1, 1, 0, 20, 34, 567890, tzinfo=datetime.UTC),
        "id:extra",
    )
    assert decode_datetime_cursor("9999999999999999999999:id") is None
