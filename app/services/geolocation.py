import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiofiles
import maxminddb

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocationInfo:
    country: str | None = None
    city: str | None = None
    latitude: str | None = None
    longitude: str | None = None


class GeolocationService:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.geoip_database_path
        self.reader: maxminddb.Reader | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return  # type: ignore[unreachable]

            if not self.db_path:
                self._initialized = True
                return

            try:
                # Load fully asynchronously into memory using aiofiles
                async with aiofiles.open(self.db_path, "rb") as f:
                    buffer = await f.read()
                # Initialize MaxMind DB from memory buffer
                self.reader = maxminddb.Reader(buffer, mode=maxminddb.MODE_MEMORY)
            except Exception as e:
                logger.warning(
                    f"GeoIP database not found or invalid at {self.db_path}: {e}"
                )

            self._initialized = True

    def resolve(self, ip_address: str) -> LocationInfo:
        if not self.reader or not ip_address:
            return LocationInfo()

        try:
            from typing import cast

            record = cast(dict[str, Any], self.reader.get(ip_address))
            if not record:
                return LocationInfo()

            country = record.get("country", {}).get("iso_code")
            city = record.get("city", {}).get("names", {}).get("en")
            location = record.get("location", {})
            lat = location.get("latitude")
            lon = location.get("longitude")

            return LocationInfo(
                country=country,
                city=city,
                latitude=str(lat) if lat is not None else None,
                longitude=str(lon) if lon is not None else None,
            )
        except ValueError:
            return LocationInfo()
        except Exception as e:
            logger.error(f"Error resolving IP {ip_address}: {e}")
            return LocationInfo()

    def close(self) -> None:
        if self.reader:
            self.reader.close()


_geolocation_service_instance: GeolocationService | None = None


async def get_geolocation_service_instance() -> GeolocationService:
    global _geolocation_service_instance
    if _geolocation_service_instance is None:
        _geolocation_service_instance = GeolocationService()

    if not _geolocation_service_instance._initialized:
        await _geolocation_service_instance.initialize()

    return _geolocation_service_instance


def shutdown_geolocation_service() -> None:
    global _geolocation_service_instance
    if _geolocation_service_instance:
        _geolocation_service_instance.close()
        _geolocation_service_instance = None
