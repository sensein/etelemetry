"""Geolocation service using MaxMind GeoLite2-City database."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GeoResult:
    """Result of a geolocation lookup."""

    city: str = "unknown"
    region: str = "unknown"
    country: str = "unknown"
    country_code: str = "XX"
    latitude: float = 0.0
    longitude: float = 0.0


def _unknown_result() -> GeoResult:
    """Return a GeoResult with default unknown values."""
    return GeoResult()


class GeoLocator:
    """Resolve IP addresses to geographic locations via MaxMind."""

    def __init__(self, db_path: str) -> None:
        self._reader = None
        path = Path(db_path)
        if not path.exists():
            logger.warning("MaxMind database not found at %s", db_path)
            return
        try:
            import geoip2.database

            self._reader = geoip2.database.Reader(str(path))
            logger.info("GeoLocator loaded MaxMind DB from %s", db_path)
        except Exception:
            logger.warning("Failed to open MaxMind database at %s", db_path, exc_info=True)

    def resolve(self, ip: str) -> GeoResult:
        """Look up an IP address and return a GeoResult.

        Returns a result with ``"unknown"`` fields when the IP cannot be
        resolved for any reason (missing DB, invalid IP, address not found).
        """
        if self._reader is None:
            return _unknown_result()

        try:
            from geoip2.errors import AddressNotFoundError

            response = self._reader.city(ip)
            return GeoResult(
                city=response.city.name or "unknown",
                region=(
                    response.subdivisions.most_specific.name
                    if response.subdivisions
                    else "unknown"
                )
                or "unknown",
                country=response.country.name or "unknown",
                country_code=response.country.iso_code or "XX",
                latitude=response.location.latitude or 0.0,
                longitude=response.location.longitude or 0.0,
            )
        except Exception as exc:
            # Covers AddressNotFoundError, ValueError (bad IP), and others
            logger.debug("Geolocation lookup failed for %s: %s", ip, exc)
            return _unknown_result()

    def close(self) -> None:
        """Close the underlying MaxMind reader."""
        if self._reader is not None:
            self._reader.close()
            self._reader = None
