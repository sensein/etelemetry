"""Geolocation service using MaxMind GeoLite2-City or DB-IP Lite database.

Tries MaxMind first (GeoLite2-City.mmdb). If that file doesn't exist,
falls back to DB-IP Lite (dbip-city-lite.mmdb), which is freely
available without registration from https://db-ip.com/db/lite.php.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


def _find_mmdb(primary_path: str) -> Path | None:
    """Find a usable MMDB file.

    Tries the configured path first, then falls back to common DB-IP
    Lite locations in the same directory or well-known paths.
    """
    primary = Path(primary_path)
    if primary.exists():
        return primary

    # Look for DB-IP Lite in the same directory as the configured path
    parent = primary.parent
    dbip_candidates = [
        parent / "dbip-city-lite.mmdb",
        parent / "dbip-city-lite-latest.mmdb",
        # Common system locations
        Path("/usr/share/GeoIP/dbip-city-lite.mmdb"),
        Path("/data/dbip-city-lite.mmdb"),
        # Local project directory
        Path("dbip-city-lite.mmdb"),
    ]
    for candidate in dbip_candidates:
        if candidate.exists():
            return candidate

    return None


class GeoLocator:
    """Resolve IP addresses to geographic locations.

    Uses MaxMind GeoLite2-City as the primary database. If that file is
    not available, falls back to DB-IP Lite (free, no registration
    required). Both use the same MMDB format readable by the ``geoip2``
    / ``maxminddb`` library.
    """

    def __init__(self, db_path: str) -> None:
        self._reader = None
        self._db_source = "none"

        mmdb_path = _find_mmdb(db_path)
        if mmdb_path is None:
            logger.warning(
                "No geolocation database found. Tried %s and DB-IP Lite "
                "fallback locations. Geolocation will return 'unknown'.",
                db_path,
            )
            return

        try:
            import geoip2.database

            self._reader = geoip2.database.Reader(str(mmdb_path))
            # Identify which database we loaded
            db_type = self._reader.metadata().database_type
            self._db_source = mmdb_path.name
            logger.info(
                "GeoLocator loaded %s database from %s",
                db_type,
                mmdb_path,
            )
        except Exception:
            logger.warning(
                "Failed to open geolocation database at %s",
                mmdb_path,
                exc_info=True,
            )

    @property
    def db_source(self) -> str:
        """Name of the loaded database file, or 'none'."""
        return self._db_source

    def resolve(self, ip: str) -> GeoResult:
        """Look up an IP address and return a GeoResult.

        Returns a result with ``"unknown"`` fields when the IP cannot be
        resolved for any reason (missing DB, invalid IP, address not found).
        """
        if self._reader is None:
            return _unknown_result()

        try:
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
            logger.debug("Geolocation lookup failed: %s", type(exc).__name__)
            return _unknown_result()

    def close(self) -> None:
        """Close the underlying reader."""
        if self._reader is not None:
            self._reader.close()
            self._reader = None
