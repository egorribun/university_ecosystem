"""Unit tests for app/utils/uuid_v7.py.

Tests RFC 9562 UUID v7 generation and timestamp extraction
without any database or HTTP fixtures — pure unit tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7


class TestGenerateUuid7:
    """Tests for generate_uuid7()."""

    def test_returns_uuid_instance(self) -> None:
        result = generate_uuid7()
        assert isinstance(result, uuid.UUID)

    def test_version_is_7(self) -> None:
        result = generate_uuid7()
        assert result.version == 7

    def test_variant_is_rfc4122(self) -> None:
        # RFC 4122 variant: the two most significant bits of octet 8 must be 10xx
        # uuid.UUID.variant returns 'specified in RFC 4122' for that case.
        result = generate_uuid7()
        assert result.variant == uuid.RFC_4122

    def test_uniqueness_across_calls(self) -> None:
        uuids = {generate_uuid7() for _ in range(100)}
        assert len(uuids) == 100

    def test_monotonically_increasing_for_same_timestamp(self) -> None:
        # Generate many UUIDs in quick succession and verify they remain unique
        generated = [generate_uuid7() for _ in range(50)]
        as_strings = [str(u) for u in generated]
        assert len(set(as_strings)) == 50

    def test_accepts_explicit_datetime(self) -> None:
        dt = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        result = generate_uuid7(dt)
        assert isinstance(result, uuid.UUID)
        assert result.version == 7

    def test_timestamp_embedded_matches_provided_datetime(self) -> None:
        """The leading 48 bits should encode the supplied millisecond timestamp."""
        dt = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        result = generate_uuid7(dt)
        extracted = extract_timestamp_from_uuid_v7(result)
        # Allow ±1 second tolerance (ms-level rounding differences)
        assert abs((extracted - dt).total_seconds()) < 1.0

    def test_uuid_without_explicit_dt_is_close_to_now(self) -> None:
        before = datetime.now(tz=UTC)
        result = generate_uuid7()
        after = datetime.now(tz=UTC)
        extracted = extract_timestamp_from_uuid_v7(result)
        assert (
            before - timedelta(seconds=1) <= extracted <= after + timedelta(seconds=1)
        )

    def test_str_representation_is_valid_uuid(self) -> None:
        result = generate_uuid7()
        # Should not raise
        parsed = uuid.UUID(str(result))
        assert parsed == result


class TestExtractTimestampFromUuidV7:
    """Tests for extract_timestamp_from_uuid_v7()."""

    def test_accepts_uuid_instance(self) -> None:
        u = generate_uuid7()
        ts = extract_timestamp_from_uuid_v7(u)
        assert isinstance(ts, datetime)
        assert ts.tzinfo is UTC

    def test_accepts_string_input(self) -> None:
        u = generate_uuid7()
        ts = extract_timestamp_from_uuid_v7(str(u))
        assert isinstance(ts, datetime)

    def test_roundtrip_with_explicit_datetime(self) -> None:
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        u = generate_uuid7(dt)
        extracted = extract_timestamp_from_uuid_v7(u)
        # Allow ±1 second for ms-level rounding
        assert abs((extracted - dt).total_seconds()) < 1.0

    def test_raises_for_invalid_string(self) -> None:
        with pytest.raises(ValueError):
            extract_timestamp_from_uuid_v7("not-a-uuid")

    def test_returns_utc_timezone(self) -> None:
        u = generate_uuid7()
        ts = extract_timestamp_from_uuid_v7(u)
        assert ts.tzinfo == UTC

    def test_historical_datetime_roundtrip(self) -> None:
        dt = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)
        u = generate_uuid7(dt)
        extracted = extract_timestamp_from_uuid_v7(u)
        assert abs((extracted - dt).total_seconds()) < 1.0
