import asyncio
import threading
from dataclasses import dataclass
from typing import Any

import aiofiles
import maxminddb

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
            except (
                FileNotFoundError,
                OSError,
            ) as e:  # RZ-22-01: narrowed — file/IO errors
                logger.warning(  # LOW-W19: lazy logging
                    "GeoIP database not found or invalid at %s: %s",
                    self.db_path,
                    e,
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
        except Exception as e:  # RZ-22-01-JUSTIFIED: handler-nak — GeoIP resolution failure returns empty LocationInfo (reviewed TD-27-04)
            logger.error(
                "Error resolving IP %s: %s", ip_address, e
            )  # LOW-W19: lazy logging
            return LocationInfo()

    def close(self) -> None:
        if self.reader:
            self.reader.close()


_geolocation_service_instance: GeolocationService | None = None
_geolocation_service_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01


async def get_geolocation_service_instance() -> GeolocationService:
    global _geolocation_service_instance
    if (
        _geolocation_service_instance is None
    ):  # RZ-33-29: fast path — no lock after init
        with _geolocation_service_lock:  # RZ-33-29: slow path — double-checked locking
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
