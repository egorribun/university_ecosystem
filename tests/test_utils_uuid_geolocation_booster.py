"""Tests for utility and service modules:
- app/utils/uuid_v7.py
- app/services/geolocation.py

Goal: bring both from ~26-30% to ~85%.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# uuid_v7.py
# ===========================================================================
from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7


class TestGenerateUuidV7:
    def test_returns_uuid_instance(self):
        result = generate_uuid7()
        assert isinstance(result, uuid.UUID)

    def test_version_is_7(self):
        result = generate_uuid7()
        assert result.version == 7

    def test_variant_is_rfc4122(self):
        """UUID variant bits should be 0b10 (RFC 4122/9562)."""
        result = generate_uuid7()
        # Variant is encoded in byte 8 (0-indexed from MSB), which sits at
        # bits 63-56 of the 128-bit integer.  Shift right 56, not 64.
        # Shifting by 64 extracts byte 7 (the version nibble region).
        variant_byte = (result.int >> 56) & 0xFF
        assert (variant_byte >> 6) == 0b10

    def test_with_explicit_datetime(self):
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = generate_uuid7(dt=dt)
        assert isinstance(result, uuid.UUID)
        assert result.version == 7

    def test_timestamp_roundtrip(self):
        """Timestamp extracted from UUIDv7 should be close to generation time."""
        # UUIDv7 stores timestamps at millisecond precision.  Truncate `before`
        # to the same precision so that sub-millisecond clock ticks between
        # datetime.now() and generate_uuid7() don't cause a false failure.
        from datetime import timedelta

        before = datetime.now(UTC)
        uid = generate_uuid7()
        after = datetime.now(UTC)

        extracted = extract_timestamp_from_uuid_v7(uid)
        before_ms = before - timedelta(microseconds=before.microsecond % 1000)
        assert before_ms <= extracted <= after

    def test_uniqueness(self):
        ids = {generate_uuid7() for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_temporal_ordering(self):
        """UUIDs generated later should have greater integer values (monotone)."""
        import time

        uid1 = generate_uuid7()
        time.sleep(0.002)  # 2ms gap
        uid2 = generate_uuid7()
        # Compare the timestamp portion (top 48 bits)
        ts1 = uid1.int >> 80
        ts2 = uid2.int >> 80
        assert ts2 >= ts1  # ms-level monotone


class TestExtractTimestampFromUuidV7:
    def test_from_uuid_object(self):
        dt = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        uid = generate_uuid7(dt=dt)
        extracted = extract_timestamp_from_uuid_v7(uid)
        # Should be within 1 second of the original (ms precision)
        diff = abs((extracted - dt).total_seconds())
        assert diff < 1.0

    def test_from_string(self):
        uid = generate_uuid7()
        uid_str = str(uid)
        extracted = extract_timestamp_from_uuid_v7(uid_str)
        assert isinstance(extracted, datetime)
        assert extracted.tzinfo == UTC

    def test_timezone_aware(self):
        uid = generate_uuid7()
        extracted = extract_timestamp_from_uuid_v7(uid)
        assert extracted.tzinfo is not None


# ===========================================================================
# geolocation.py
# ===========================================================================

import app.services.geolocation as geo_mod
from app.services.geolocation import (
    GeolocationService,
    LocationInfo,
    get_geolocation_service_instance,
    shutdown_geolocation_service,
)


class TestLocationInfo:
    def test_default_none_values(self):
        info = LocationInfo()
        assert info.country is None
        assert info.city is None
        assert info.latitude is None
        assert info.longitude is None

    def test_with_values(self):
        info = LocationInfo(
            country="US", city="NYC", latitude="40.7", longitude="-74.0"
        )
        assert info.country == "US"
        assert info.city == "NYC"


class TestGeolocationServiceResolve:
    def test_resolve_no_reader_returns_empty(self):
        service = GeolocationService.__new__(GeolocationService)
        service.reader = None
        result = service.resolve("1.2.3.4")
        assert isinstance(result, LocationInfo)
        assert result.country is None

    def test_resolve_empty_ip_returns_empty(self):
        service = GeolocationService.__new__(GeolocationService)
        service.reader = MagicMock()
        result = service.resolve("")
        assert result.country is None

    def test_resolve_with_valid_record(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        mock_reader.get.return_value = {
            "country": {"iso_code": "US"},
            "city": {"names": {"en": "New York"}},
            "location": {"latitude": 40.7128, "longitude": -74.0060},
        }
        service.reader = mock_reader

        result = service.resolve("8.8.8.8")
        assert result.country == "US"
        assert result.city == "New York"
        assert result.latitude == "40.7128"
        assert result.longitude == "-74.006"

    def test_resolve_with_empty_record(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        mock_reader.get.return_value = None
        service.reader = mock_reader

        result = service.resolve("1.2.3.4")
        assert result.country is None

    def test_resolve_value_error_returns_empty(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        mock_reader.get.side_effect = ValueError("invalid IP")
        service.reader = mock_reader

        result = service.resolve("invalid-ip")
        assert result.country is None

    def test_resolve_generic_exception_returns_empty(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        mock_reader.get.side_effect = RuntimeError("unexpected")
        service.reader = mock_reader

        result = service.resolve("1.2.3.4")
        assert result.country is None

    def test_resolve_partial_record_no_city(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        mock_reader.get.return_value = {
            "country": {"iso_code": "DE"},
            "city": {},  # no "names"
            "location": {},  # no lat/lon
        }
        service.reader = mock_reader

        result = service.resolve("5.6.7.8")
        assert result.country == "DE"
        assert result.city is None
        assert result.latitude is None


class TestGeolocationServiceClose:
    def test_close_no_reader(self):
        service = GeolocationService.__new__(GeolocationService)
        service.reader = None
        service.close()  # should not raise

    def test_close_with_reader(self):
        service = GeolocationService.__new__(GeolocationService)
        mock_reader = MagicMock()
        service.reader = mock_reader
        service.close()
        mock_reader.close.assert_called_once()


class TestGeolocationServiceInitialize:
    @pytest.mark.asyncio
    async def test_initialize_no_db_path(self):
        """If no db_path, marks as initialized but leaves reader None."""
        service = GeolocationService.__new__(GeolocationService)
        service._initialized = False
        service._init_lock = __import__("asyncio").Lock()
        service.reader = None

        with patch("app.services.geolocation.settings") as mock_settings:
            mock_settings.geoip_database_path = None
            service.db_path = None
            await service.initialize()

        assert service._initialized
        assert service.reader is None

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Should return early without re-initializing."""
        service = GeolocationService.__new__(GeolocationService)
        service._initialized = True
        service.reader = MagicMock()
        original_reader = service.reader

        await service.initialize()  # should no-op
        assert service.reader is original_reader

    @pytest.mark.asyncio
    async def test_initialize_file_not_found(self):
        """FileNotFoundError should be caught and logged."""
        import asyncio as aio

        service = GeolocationService.__new__(GeolocationService)
        service._initialized = False
        service._init_lock = aio.Lock()
        service.reader = None
        service.db_path = "/nonexistent/path/geoip.mmdb"

        with patch(
            "app.services.geolocation.aiofiles.open",
            side_effect=FileNotFoundError("not found"),
        ):
            await service.initialize()

        assert service._initialized
        assert service.reader is None


class TestShutdownGeolocationService:
    def test_shutdown_when_no_instance(self):
        original = geo_mod._geolocation_service_instance
        geo_mod._geolocation_service_instance = None
        try:
            shutdown_geolocation_service()  # should not raise
        finally:
            geo_mod._geolocation_service_instance = original

    def test_shutdown_closes_and_clears(self):
        original = geo_mod._geolocation_service_instance
        mock_service = MagicMock()
        geo_mod._geolocation_service_instance = mock_service
        try:
            shutdown_geolocation_service()
            mock_service.close.assert_called_once()
            assert geo_mod._geolocation_service_instance is None
        finally:
            geo_mod._geolocation_service_instance = original


@pytest.mark.asyncio
async def test_get_geolocation_service_instance_returns_service():
    """Should return a GeolocationService that is initialized."""
    original = geo_mod._geolocation_service_instance
    geo_mod._geolocation_service_instance = None

    try:
        with patch("app.services.geolocation.settings") as mock_settings:
            mock_settings.geoip_database_path = None
            service = await get_geolocation_service_instance()
            assert isinstance(service, GeolocationService)
            assert service._initialized
    finally:
        geo_mod._geolocation_service_instance = original
