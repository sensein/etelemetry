"""Usage recording service — content-addressed upsert into version_checks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from etelemetry_server.models import VersionCheck
from etelemetry_server.services.geolocation import GeoResult

logger = logging.getLogger(__name__)


def _compute_time_bucket(time_bucket_hours: int) -> datetime:
    """Truncate the current UTC time to the nearest *time_bucket_hours* boundary."""
    now = datetime.now(timezone.utc)
    # Truncate to the start of the current bucket
    total_hours = now.hour
    bucket_hour = (total_hours // time_bucket_hours) * time_bucket_hours
    return now.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)


async def record_usage(
    session: AsyncSession,
    project_id: int,
    version: str,
    geo_result: GeoResult,
    is_ci: bool,
    time_bucket_hours: int,
) -> None:
    """Record a version check using a content-addressed upsert.

    If a row with the same (project_id, version, city, region, country_code,
    is_ci, time_bucket) already exists, its ``count`` is incremented.
    """
    time_bucket = _compute_time_bucket(time_bucket_hours)

    values = {
        "project_id": project_id,
        "version": version or "unknown",
        "city": geo_result.city,
        "region": geo_result.region,
        "country": geo_result.country,
        "country_code": geo_result.country_code,
        "latitude": geo_result.latitude,
        "longitude": geo_result.longitude,
        "is_ci": is_ci,
        "time_bucket": time_bucket,
        "count": 1,
    }

    stmt = pg_insert(VersionCheck).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_version_check_content_address",
        set_={"count": VersionCheck.__table__.c.count + 1},
    )

    await session.execute(stmt)
