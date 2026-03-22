"""Aggregation service for pre-computing usage statistics.

Queries version_checks, groups by project/version/location/period,
and upserts results into usage_aggregates.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from etelemetry_server.models import Project, UsageAggregate, VersionCheck

logger = logging.getLogger(__name__)


def _truncate_date(dt: datetime.datetime, granularity: str) -> datetime.date:
    """Truncate a datetime to the start of the given granularity period."""
    d = dt.date() if isinstance(dt, datetime.datetime) else dt
    if granularity == "daily":
        return d
    elif granularity == "weekly":
        # Start of ISO week (Monday)
        return d - datetime.timedelta(days=d.weekday())
    elif granularity == "monthly":
        return d.replace(day=1)
    else:
        raise ValueError(f"Unknown granularity: {granularity}")


async def compute_aggregates(
    session: AsyncSession,
    granularity: str,
    date_from: datetime.date,
    date_to: datetime.date,
) -> int:
    """Query version_checks, group by project/version/location/period,
    and upsert into usage_aggregates.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    granularity : str
        One of 'daily', 'weekly', 'monthly'.
    date_from : datetime.date
        Start of the date range (inclusive).
    date_to : datetime.date
        End of the date range (inclusive).

    Returns
    -------
    int
        Number of aggregate rows upserted.
    """
    from_dt = datetime.datetime.combine(date_from, datetime.time.min)
    to_dt = datetime.datetime.combine(
        date_to + datetime.timedelta(days=1), datetime.time.min
    )

    # Query version_checks grouped by project, version, country_code, region
    stmt = (
        select(
            VersionCheck.project_id,
            VersionCheck.version,
            VersionCheck.country_code,
            VersionCheck.region,
            func.sum(VersionCheck.count).label("total_count"),
            func.count(
                func.distinct(
                    func.coalesce(VersionCheck.city, "")
                    + ":"
                    + func.coalesce(VersionCheck.region, "")
                    + ":"
                    + func.coalesce(VersionCheck.country_code, "")
                )
            ).label("unique_locations"),
            func.sum(
                # Sum count where is_ci is True
                VersionCheck.count * func.cast(VersionCheck.is_ci, type_=VersionCheck.count.type)
            ).label("ci_count"),
            VersionCheck.time_bucket,
        )
        .where(
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
        )
        .group_by(
            VersionCheck.project_id,
            VersionCheck.version,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.time_bucket,
        )
    )

    result = await session.execute(stmt)
    rows = result.all()

    # Group rows by (project_id, version, country_code, region, period_start)
    aggregated: dict[tuple, dict] = {}
    for row in rows:
        period_start = _truncate_date(row.time_bucket, granularity)
        key = (
            row.project_id,
            row.version,
            row.country_code,
            row.region,
            period_start,
        )
        if key not in aggregated:
            aggregated[key] = {
                "total_count": 0,
                "unique_locations": 0,
                "ci_count": 0,
                "location_set": set(),
            }
        agg = aggregated[key]
        agg["total_count"] += row.total_count or 0
        agg["ci_count"] += row.ci_count or 0
        # Track unique location strings
        loc_str = f"{row.country_code}:{row.region}"
        agg["location_set"].add(loc_str)
        agg["unique_locations"] = len(agg["location_set"])

    # Delete existing aggregates for this granularity and date range, then insert
    await session.execute(
        delete(UsageAggregate).where(
            UsageAggregate.granularity == granularity,
            UsageAggregate.period_start >= date_from,
            UsageAggregate.period_start <= date_to,
        )
    )

    count = 0
    for key, agg in aggregated.items():
        project_id, version, country_code, region, period_start = key
        aggregate = UsageAggregate(
            project_id=project_id,
            version=version,
            country_code=country_code,
            region=region,
            granularity=granularity,
            period_start=period_start,
            total_count=agg["total_count"],
            unique_locations=agg["unique_locations"],
            ci_count=agg["ci_count"],
        )
        session.add(aggregate)
        count += 1

    await session.flush()
    logger.info(
        "Computed %d %s aggregates for %s to %s",
        count,
        granularity,
        date_from,
        date_to,
    )
    return count


async def run_tiered_aggregation(
    session: AsyncSession,
    daily_threshold_days: int = 30,
    weekly_threshold_days: int = 365,
) -> dict[str, int]:
    """Compute tiered aggregations: daily for recent, weekly for medium, monthly for old.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    daily_threshold_days : int
        Number of days back for daily aggregation (default 30).
    weekly_threshold_days : int
        Number of days back for weekly aggregation (default 365).

    Returns
    -------
    dict[str, int]
        Mapping of granularity to number of rows upserted.
    """
    today = datetime.date.today()
    results = {}

    # Daily: last N days
    daily_from = today - datetime.timedelta(days=daily_threshold_days)
    results["daily"] = await compute_aggregates(
        session, "daily", daily_from, today
    )

    # Weekly: from daily_threshold to weekly_threshold days ago
    weekly_from = today - datetime.timedelta(days=weekly_threshold_days)
    weekly_to = daily_from - datetime.timedelta(days=1)
    if weekly_to >= weekly_from:
        results["weekly"] = await compute_aggregates(
            session, "weekly", weekly_from, weekly_to
        )
    else:
        results["weekly"] = 0

    # Monthly: older than weekly_threshold days
    # Find the earliest version_check
    stmt = select(func.min(VersionCheck.time_bucket))
    result = await session.execute(stmt)
    earliest = result.scalar()
    if earliest is not None:
        earliest_date = earliest.date() if isinstance(earliest, datetime.datetime) else earliest
        monthly_to = weekly_from - datetime.timedelta(days=1)
        if monthly_to >= earliest_date:
            results["monthly"] = await compute_aggregates(
                session, "monthly", earliest_date, monthly_to
            )
        else:
            results["monthly"] = 0
    else:
        results["monthly"] = 0

    logger.info("Tiered aggregation complete: %s", results)
    return results
