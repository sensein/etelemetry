"""Dashboard routes — HTML pages and JSON API endpoints."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from etelemetry_server.db import get_db
from etelemetry_server.models import Project, UsageAggregate, VersionCheck

logger = logging.getLogger(__name__)

router = APIRouter()

# Template and static file paths
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
_TEMPLATE_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@router.get("/dashboard/", response_class=HTMLResponse)
async def dashboard_index(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Render the project list HTML page."""
    stmt = (
        select(
            Project.owner,
            Project.repo,
            func.coalesce(func.sum(VersionCheck.count), 0).label("total_checks"),
        )
        .outerjoin(VersionCheck, VersionCheck.project_id == Project.id)
        .where(Project.active.is_(True))
        .group_by(Project.owner, Project.repo)
        .order_by(Project.owner, Project.repo)
    )
    result = await session.execute(stmt)
    projects = [
        {"owner": row.owner, "repo": row.repo, "total_checks": int(row.total_checks)}
        for row in result.all()
    ]
    return templates.TemplateResponse(
        "projects.html",
        {"request": request, "projects": projects},
    )


@router.get("/dashboard/project/{owner}/{repo}", response_class=HTMLResponse)
async def dashboard_project_detail(
    request: Request,
    owner: str,
    repo: str,
    session: AsyncSession = Depends(get_db),
):
    """Render the project detail HTML page."""
    # Fetch project
    stmt = select(Project).where(Project.owner == owner, Project.repo == repo)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        return HTMLResponse(content="<h1>Project not found</h1>", status_code=404)

    # Total checks
    total_stmt = (
        select(func.coalesce(func.sum(VersionCheck.count), 0))
        .where(VersionCheck.project_id == project.id)
    )
    total_result = await session.execute(total_stmt)
    total_checks = int(total_result.scalar() or 0)

    # Unique versions
    versions_stmt = (
        select(func.count(distinct(VersionCheck.version)))
        .where(VersionCheck.project_id == project.id)
    )
    versions_result = await session.execute(versions_stmt)
    unique_versions = int(versions_result.scalar() or 0)

    # Unique locations
    locations_stmt = (
        select(
            func.count(
                distinct(
                    func.coalesce(VersionCheck.country_code, "")
                    + ":"
                    + func.coalesce(VersionCheck.region, "")
                    + ":"
                    + func.coalesce(VersionCheck.city, "")
                )
            )
        )
        .where(VersionCheck.project_id == project.id)
    )
    locations_result = await session.execute(locations_stmt)
    unique_locations = int(locations_result.scalar() or 0)

    # Version distribution
    version_dist_stmt = (
        select(
            VersionCheck.version,
            func.sum(VersionCheck.count).label("count"),
        )
        .where(VersionCheck.project_id == project.id)
        .group_by(VersionCheck.version)
        .order_by(func.sum(VersionCheck.count).desc())
    )
    version_dist_result = await session.execute(version_dist_stmt)
    by_version = [
        {"version": row.version, "count": int(row.count)}
        for row in version_dist_result.all()
    ]

    # Geographic summary
    geo_stmt = (
        select(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
            func.sum(VersionCheck.count).label("count"),
        )
        .where(VersionCheck.project_id == project.id)
        .group_by(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
        )
        .order_by(func.sum(VersionCheck.count).desc())
    )
    geo_result = await session.execute(geo_stmt)
    by_location = [
        {
            "country": row.country,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "count": int(row.count),
        }
        for row in geo_result.all()
    ]

    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request,
            "owner": owner,
            "repo": repo,
            "total_checks": total_checks,
            "unique_versions": unique_versions,
            "unique_locations": unique_locations,
            "by_version": by_version,
            "by_location": by_location,
        },
    )


# ---------------------------------------------------------------------------
# JSON API endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard/api/projects")
async def api_projects(
    session: AsyncSession = Depends(get_db),
):
    """Return list of all tracked projects with total check counts."""
    stmt = (
        select(
            Project.owner,
            Project.repo,
            func.coalesce(func.sum(VersionCheck.count), 0).label("total_checks"),
        )
        .outerjoin(VersionCheck, VersionCheck.project_id == Project.id)
        .where(Project.active.is_(True))
        .group_by(Project.owner, Project.repo)
        .order_by(Project.owner, Project.repo)
    )
    result = await session.execute(stmt)
    projects = [
        {"owner": row.owner, "repo": row.repo, "total_checks": int(row.total_checks)}
        for row in result.all()
    ]
    return {"projects": projects}


@router.get("/dashboard/api/stats/{owner}/{repo}")
async def api_stats(
    owner: str,
    repo: str,
    session: AsyncSession = Depends(get_db),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    granularity: Optional[str] = Query(None),
):
    """Return stats for a specific project.

    Response shape matches contracts/api.md exactly.
    """
    # Find project
    stmt = select(Project).where(Project.owner == owner, Project.repo == repo)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        return JSONResponse(
            status_code=404,
            content={"error": "project not found"},
        )

    # Parse date range
    today = datetime.date.today()
    try:
        from_date = datetime.date.fromisoformat(date_from) if date_from else None
    except ValueError:
        from_date = None
    try:
        to_date = datetime.date.fromisoformat(date_to) if date_to else None
    except ValueError:
        to_date = None

    if from_date is None:
        from_date = today - datetime.timedelta(days=90)
    if to_date is None:
        to_date = today

    from_dt = datetime.datetime.combine(from_date, datetime.time.min)
    to_dt = datetime.datetime.combine(to_date + datetime.timedelta(days=1), datetime.time.min)

    # Auto-determine granularity if not specified
    if granularity not in ("daily", "weekly", "monthly"):
        span_days = (to_date - from_date).days
        if span_days <= 31:
            granularity = "daily"
        elif span_days <= 365:
            granularity = "weekly"
        else:
            granularity = "monthly"

    # Total checks in range
    total_stmt = (
        select(func.coalesce(func.sum(VersionCheck.count), 0))
        .where(
            VersionCheck.project_id == project.id,
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
        )
    )
    total_result = await session.execute(total_stmt)
    total_checks = int(total_result.scalar() or 0)

    # By version
    version_stmt = (
        select(
            VersionCheck.version,
            func.sum(VersionCheck.count).label("count"),
        )
        .where(
            VersionCheck.project_id == project.id,
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
        )
        .group_by(VersionCheck.version)
        .order_by(func.sum(VersionCheck.count).desc())
    )
    version_result = await session.execute(version_stmt)
    by_version = [
        {"version": row.version, "count": int(row.count)}
        for row in version_result.all()
    ]

    # By location
    location_stmt = (
        select(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
            func.avg(VersionCheck.latitude).label("lat"),
            func.avg(VersionCheck.longitude).label("lon"),
            func.sum(VersionCheck.count).label("count"),
        )
        .where(
            VersionCheck.project_id == project.id,
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
        )
        .group_by(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
        )
        .order_by(func.sum(VersionCheck.count).desc())
    )
    location_result = await session.execute(location_stmt)
    by_location = [
        {
            "country": row.country,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "lat": float(row.lat) if row.lat is not None else None,
            "lon": float(row.lon) if row.lon is not None else None,
            "count": int(row.count),
        }
        for row in location_result.all()
    ]

    # Timeline
    timeline = await _compute_timeline(
        session, project.id, from_dt, to_dt, granularity
    )

    return {
        "project": f"{owner}/{repo}",
        "period": {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        },
        "total_checks": total_checks,
        "by_version": by_version,
        "by_location": by_location,
        "timeline": timeline,
    }


@router.get("/dashboard/api/geo/{owner}/{repo}")
async def api_geo(
    owner: str,
    repo: str,
    session: AsyncSession = Depends(get_db),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    granularity: Optional[str] = Query(None),
):
    """Return GeoJSON FeatureCollection for map visualization."""
    # Find project
    stmt = select(Project).where(Project.owner == owner, Project.repo == repo)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        return JSONResponse(
            status_code=404,
            content={"error": "project not found"},
        )

    # Parse date range
    today = datetime.date.today()
    try:
        from_date = datetime.date.fromisoformat(date_from) if date_from else None
    except ValueError:
        from_date = None
    try:
        to_date = datetime.date.fromisoformat(date_to) if date_to else None
    except ValueError:
        to_date = None

    if from_date is None:
        from_date = today - datetime.timedelta(days=90)
    if to_date is None:
        to_date = today

    from_dt = datetime.datetime.combine(from_date, datetime.time.min)
    to_dt = datetime.datetime.combine(to_date + datetime.timedelta(days=1), datetime.time.min)

    # Query locations with coordinates
    location_stmt = (
        select(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
            func.avg(VersionCheck.latitude).label("lat"),
            func.avg(VersionCheck.longitude).label("lon"),
            func.sum(VersionCheck.count).label("count"),
        )
        .where(
            VersionCheck.project_id == project.id,
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
            VersionCheck.latitude.isnot(None),
            VersionCheck.longitude.isnot(None),
        )
        .group_by(
            VersionCheck.country,
            VersionCheck.country_code,
            VersionCheck.region,
            VersionCheck.city,
        )
    )
    location_result = await session.execute(location_stmt)

    features = []
    for row in location_result.all():
        if row.lat is not None and row.lon is not None:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row.lon), float(row.lat)],
                    },
                    "properties": {
                        "country": row.country,
                        "country_code": row.country_code,
                        "region": row.region,
                        "city": row.city,
                        "count": int(row.count),
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _compute_timeline(
    session: AsyncSession,
    project_id: int,
    from_dt: datetime.datetime,
    to_dt: datetime.datetime,
    granularity: str,
) -> list[dict]:
    """Compute timeline data grouped by the given granularity."""
    # Query raw version_checks and bucket in Python for DB portability
    stmt = (
        select(
            VersionCheck.time_bucket,
            func.sum(VersionCheck.count).label("count"),
        )
        .where(
            VersionCheck.project_id == project_id,
            VersionCheck.time_bucket >= from_dt,
            VersionCheck.time_bucket < to_dt,
        )
        .group_by(VersionCheck.time_bucket)
        .order_by(VersionCheck.time_bucket)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Bucket into periods
    buckets: dict[str, int] = {}
    for row in rows:
        ts = row.time_bucket
        if isinstance(ts, str):
            ts = datetime.datetime.fromisoformat(ts)
        d = ts.date() if isinstance(ts, datetime.datetime) else ts
        period_label = _period_label(d, granularity)
        buckets[period_label] = buckets.get(period_label, 0) + int(row.count)

    # Sort and return
    timeline = [
        {"period": period, "count": count}
        for period, count in sorted(buckets.items())
    ]
    return timeline


def _period_label(d: datetime.date, granularity: str) -> str:
    """Return a human-readable period label for the given date and granularity."""
    if granularity == "daily":
        return d.isoformat()
    elif granularity == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    elif granularity == "monthly":
        return f"{d.year}-{d.month:02d}"
    else:
        return d.isoformat()
