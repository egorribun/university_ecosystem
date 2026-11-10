"""GeoIP initialization fails soft only for known file/database failures."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from maxminddb.errors import InvalidDatabaseError
from structlog.testing import capture_logs

import app.services.geolocation as geo
from app.core.di.infrastructure import InfrastructureProvider
from app.core.logging import get_logger

_VALID_DATABASE = (
    Path(__file__).parent / "fixtures" / "geoip" / "MaxMind-DB-test-ipv4-24.mmdb"
)


@pytest.mark.parametrize("kind", ["empty", "garbage", "truncated"])
async def test_corrupt_database_provider_degrades_once_and_recovers_after_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A real Reader failure must not poison every later provider request."""
    valid_data = _VALID_DATABASE.read_bytes()
    payloads = {
        "empty": b"",
        "garbage": b"synthetic private database contents",
        "truncated": valid_data[: len(valid_data) // 2],
    }
    database = tmp_path / "private-configuration-path.mmdb"
    database.write_bytes(payloads[kind])
    monkeypatch.setattr(geo.settings, "geoip_database_path", str(database))
    monkeypatch.setattr(geo, "_geolocation_service_instance", None)
    provider = InfrastructureProvider()

    with capture_logs() as logs:
        # A fresh real logger uses this test's capture processor, even when
        # another test has already bound the module's cached logger.
        monkeypatch.setattr(geo, "logger", get_logger(geo.__name__))
        services = await asyncio.gather(
            *(provider.geolocation_service() for _ in range(8)),
            return_exceptions=True,
        )
        assert all(isinstance(result, geo.GeolocationService) for result in services)
        service = services[0]
        assert isinstance(service, geo.GeolocationService)
        assert all(result is service for result in services)
        assert service._initialized is True
        assert service.reader is None
        assert service.resolve("192.0.2.1") == geo.LocationInfo()

        # Like a missing file, invalid data remains disabled until shutdown.
        # Replacing the file must not trigger a second load or warning.
        database.write_bytes(valid_data)
        assert await provider.geolocation_service() is service
        await service.initialize()
        assert service.reader is None

    assert len(logs) == 1
    assert logs[0]["log_level"] == "warning"
    assert "geoip" in logs[0]["event"].lower()
    assert "invalid" in logs[0]["event"].lower()
    assert str(database) not in str(logs)
    assert database.name not in str(logs)
    assert "synthetic private database contents" not in str(logs)
    assert "exception" not in logs[0]
    assert "exc_info" not in logs[0]

    geo.shutdown_geolocation_service()
    try:
        recovered = await provider.geolocation_service()
        assert recovered is not service
        assert recovered._initialized is True
        assert recovered.reader is not None
        assert recovered.reader.get("1.1.1.1") == {"ip": "1.1.1.1"}
    finally:
        geo.shutdown_geolocation_service()


@pytest.mark.parametrize("kind", ["missing", "directory"])
async def test_file_errors_still_disable_optional_geolocation(
    tmp_path: Path, kind: str
) -> None:
    database = tmp_path / "missing.mmdb" if kind == "missing" else tmp_path
    service = geo.GeolocationService(db_path=str(database))

    await service.initialize()

    assert service._initialized is True
    assert service.reader is None
    assert service.resolve("192.0.2.1") == geo.LocationInfo()


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, MemoryError])
async def test_unexpected_reader_errors_propagate_and_allow_a_later_retry(
    error_type: type[Exception],
) -> None:
    """Broadening the catch to RuntimeError or Exception must fail this test."""
    service = geo.GeolocationService(db_path=str(_VALID_DATABASE))
    failure = error_type("synthetic unexpected reader failure")

    # Only inject the unexpected Reader failure. File IO and the retry use
    # the real dependencies; no malformed MMDB produces these exact errors.
    with patch.object(geo.maxminddb, "Reader", side_effect=failure):
        with pytest.raises(error_type) as error:
            await service.initialize()

    assert error.value is failure
    assert service._initialized is False
    assert service.reader is None
    try:
        await service.initialize()
        assert service._initialized is True
        assert service.reader is not None
        assert service.reader.get("1.1.1.1") == {"ip": "1.1.1.1"}
    finally:
        service.close()


async def test_invalid_database_warning_omits_exception_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = geo.GeolocationService(db_path=str(_VALID_DATABASE))
    failure = InvalidDatabaseError("synthetic-private-parser-detail")

    with capture_logs() as logs:
        monkeypatch.setattr(geo, "logger", get_logger(geo.__name__))
        with patch.object(geo.maxminddb, "Reader", side_effect=failure):
            await service.initialize()

    assert service._initialized is True
    assert service.resolve("192.0.2.1") == geo.LocationInfo()
    assert len(logs) == 1
    assert logs[0]["log_level"] == "warning"
    assert "synthetic-private-parser-detail" not in str(logs)
    assert str(_VALID_DATABASE) not in str(logs)
    assert "exception" not in logs[0]
    assert "exc_info" not in logs[0]
