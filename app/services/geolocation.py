import logging
from dataclasses import dataclass

import geoip2.database
from geoip2.errors import AddressNotFoundError

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
        self.reader = None
        if self.db_path:
            try:
                self.reader = geoip2.database.Reader(self.db_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    f"GeoIP database not found or invalid at {self.db_path}: {e}"
                )

    def resolve(self, ip_address: str) -> LocationInfo:
        if not self.reader or not ip_address:
            return LocationInfo()

        try:
            response = self.reader.city(ip_address)
            return LocationInfo(
                country=response.country.iso_code,
                city=response.city.name,
                latitude=(
                    str(response.location.latitude)
                    if response.location.latitude
                    else None
                ),
                longitude=(
                    str(response.location.longitude)
                    if response.location.longitude
                    else None
                ),
            )
        except AddressNotFoundError:
            return LocationInfo()
        except Exception as e:
            logger.error(f"Error resolving IP {ip_address}: {e}")
            return LocationInfo()

    def close(self):
        if self.reader:
            self.reader.close()
