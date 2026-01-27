from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.notifications import (
    _coerce_bool,
    _coerce_int,
    _decode_cursor,
    _encode_cursor,
    _ensure_utc,
    _fetch_notification_rows,
    _fetch_notification_rows_fallback,
    _is_missing_column_error,
    _localized_notification_field,
    _parse_datetime,
)


class MockSQLAlchemyError(SQLAlchemyError):
    def __init__(self, message):
        self.orig = Exception(message)


def test_is_missing_column_error():
    assert _is_missing_column_error(MockSQLAlchemyError("no such column: title_en"))
    assert _is_missing_column_error(MockSQLAlchemyError("Unknown column 'x'"))
    assert not _is_missing_column_error(MockSQLAlchemyError("syntax error"))


def test_parse_datetime():
    # Test valid inputs
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert _parse_datetime(dt) == dt

    # Naive becomes UTC
    naive = datetime(2023, 1, 1, 12, 0, 0)
    expected = naive.replace(tzinfo=UTC)
    assert _parse_datetime(naive) == expected

    # Timestamp
    ts = dt.timestamp()
    assert _parse_datetime(ts) == dt

    # Milliseconds timestamp
    assert _parse_datetime(ts * 1000) == dt

    # ISO String
    assert _parse_datetime("2023-01-01T12:00:00+00:00") == dt
    assert _parse_datetime("2023-01-01T12:00:00Z") == dt

    # Numeric string
    assert _parse_datetime(str(ts)) == dt

    # Invalid inputs
    assert _parse_datetime(None) is None
    assert _parse_datetime("invalid") is None
    assert _parse_datetime([]) is None


def test_ensure_utc():
    # If None, returns now
    res = _ensure_utc(None)
    assert isinstance(res, datetime)
    assert res.tzinfo == UTC

    # If valid, returns valid
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert _ensure_utc(dt) == dt


def test_coerce_bool():
    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False
    assert _coerce_bool(1) is True
    assert _coerce_bool(0) is False
    assert _coerce_bool("true") is True
    assert _coerce_bool("1") is True
    assert _coerce_bool("yes") is True
    assert _coerce_bool("false") is False
    assert _coerce_bool("0") is False
    assert _coerce_bool("no") is False
    # Fallback
    assert _coerce_bool(object()) is True
    assert _coerce_bool(None) is False


def test_coerce_int():
    assert _coerce_int(10) == 10
    assert _coerce_int("10") == 10
    assert _coerce_int(True) == 1
    assert _coerce_int(False) == 0
    assert _coerce_int(10.5) == 10
    assert _coerce_int("10.5") == 10

    # Invalid / default
    assert _coerce_int(None, default=5) == 5
    assert _coerce_int("invalid", default=5) == 5
    assert _coerce_int([], default=5) == 5


def test_localized_notification_field():
    # Full data
    assert _localized_notification_field("en", "Ru", "En") == "En"
    assert _localized_notification_field("ru", "Ru", "En") == "Ru"

    # Fallback to English if clean
    assert _localized_notification_field("fr", "Ru", "En") == "En"

    # Partial data
    assert _localized_notification_field("en", "Ru", None) == "Ru"
    assert _localized_notification_field("en", None, "En") == "En"

    # Required logic
    assert _localized_notification_field("en", None, None, required=True) == ""
    assert _localized_notification_field("en", "Ru", None, required=True) == "Ru"


def test_decode_cursor():
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    # Use helper to encode
    cursor_str = _encode_cursor(dt, 123)

    res = _decode_cursor(cursor_str)
    assert res is not None
    assert res[0] == dt
    assert res[1] == 123

    assert _decode_cursor(None) is None
    assert _decode_cursor("invalid") is None


@pytest.mark.asyncio
async def test_fetch_notification_rows_fallback():
    # Mock DB session
    mock_db = AsyncMock()

    # Mock _existing_notification_columns to return minimal columns
    # We patch the function where it is imported/defined
    with patch(
        "app.api.notifications._existing_notification_columns",
        return_value={"id", "title", "user_id"},
    ) as mock_cols:
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"id": 1, "title": "Test", "user_id": 1, "read": False}
        ]
        mock_db.execute.return_value = mock_result

        rows, cols = await _fetch_notification_rows_fallback(
            mock_db, user_id=1, limit=10, cursor_info=None
        )

        assert cols == {"id", "title", "user_id"}
        assert len(rows) == 1
        assert rows[0]["title"] == "Test"

        # Verify call arguments
        # We can't easily check the exact SQL object equality, but we know it executed something
        assert mock_db.execute.called


@pytest.mark.asyncio
async def test_fetch_notification_rows_handles_missing_column_error():
    # Simulate first attempt failing with missing column, triggering fallback
    mock_db = AsyncMock()

    # First call raises SQLAlchemyError with "no such column"
    mock_db.execute.side_effect = [
        MockSQLAlchemyError("no such column: title_en"),  # Primary attempt
        MagicMock(
            mappings=lambda: MagicMock(all=lambda: [{"id": 1, "title": "Fallback"}])
        ),  # Fallback attempt
    ]

    with patch(
        "app.api.notifications._existing_notification_columns",
        return_value={"id", "title", "user_id"},
    ):
        rows, cols = await _fetch_notification_rows(
            mock_db, user_id=1, limit=10, cursor_info=None
        )

        assert len(rows) == 1
        assert rows[0]["title"] == "Fallback"
        # Since fallback was used, the cols set should be returned
        assert cols == {"id", "title", "user_id"}
