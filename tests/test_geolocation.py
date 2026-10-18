from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.geolocation import (
    GeolocationService,
    LocationInfo,
    get_geolocation_service_instance,
    shutdown_geolocation_service,
)


@pytest.mark.anyio
async def test_geolocation_service_init_no_path():
    service = GeolocationService(db_path="")
    await service.initialize()
    assert service._initialized is True
    assert service.reader is None


@pytest.mark.anyio
async def test_geolocation_service_init_success():
    fixture_path = (
        Path(__file__).parent / "fixtures" / "geoip" / "MaxMind-DB-test-ipv4-24.mmdb"
    )
    service = GeolocationService(db_path=str(fixture_path))

    await service.initialize()

    assert service._initialized is True
    assert service.reader is not None
    try:
        assert service.reader.get("1.1.1.1") == {"ip": "1.1.1.1"}
    finally:
        service.close()


@pytest.mark.anyio
async def test_geolocation_service_init_file_not_found():
    service = GeolocationService(db_path="/mock/nonexistent.mmdb")

    with patch("aiofiles.open", side_effect=FileNotFoundError()):
        await service.initialize()
        assert service._initialized is True
        assert service.reader is None


@pytest.mark.anyio
async def test_geolocation_service_resolve():
    service = GeolocationService(db_path="/mock/path.mmdb")
    mock_reader = MagicMock()
    service.reader = mock_reader

    # Case 1: Empty IP or missing reader
    service.reader = None
    assert service.resolve("") == LocationInfo()
    assert service.resolve("8.8.8.8") == LocationInfo()

    service.reader = mock_reader

    # Case 2: No record found
    mock_reader.get.return_value = None
    assert service.resolve("8.8.8.8") == LocationInfo()

    # Case 3: Successful record resolved
    mock_reader.get.return_value = {
        "country": {"iso_code": "US"},
        "city": {"names": {"en": "Mountain View"}},
        "location": {"latitude": 37.4, "longitude": -122.0},
    }
    info = service.resolve("8.8.8.8")
    assert info.country == "US"
    assert info.city == "Mountain View"
    assert info.latitude == "37.4"
    assert info.longitude == "-122.0"

    # Case 4: Exception handled in get
    mock_reader.get.side_effect = ValueError("invalid IP")
    assert service.resolve("invalid-ip") == LocationInfo()


@pytest.mark.anyio
async def test_geolocation_service_close():
    service = GeolocationService()
    mock_reader = MagicMock()
    service.reader = mock_reader

    service.close()
    mock_reader.close.assert_called_once()


@pytest.mark.anyio
async def test_geolocation_singleton_and_shutdown():
    async def mock_init(self):
        self._initialized = True

    with patch.object(GeolocationService, "initialize", mock_init):
        # Get instance
        inst1 = await get_geolocation_service_instance()
        inst2 = await get_geolocation_service_instance()

        assert inst1 is inst2

        # Shutdown
        with patch.object(inst1, "close") as mock_close:
            shutdown_geolocation_service()
            mock_close.assert_called_once()
            # Next call creates a new instance
            inst3 = await get_geolocation_service_instance()
            assert inst3 is not inst1
            shutdown_geolocation_service()
