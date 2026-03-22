"""Projects route — version check endpoint."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from etelemetry_server.db import get_db
from etelemetry_server.models import Project
from etelemetry_server.services.geolocation import GeoLocator, GeoResult, _unknown_result
from etelemetry_server.services.usage_recorder import record_usage
from etelemetry_server.services.version_checker import VersionChecker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{owner}/{repo}")
async def get_project_version(
    owner: str,
    repo: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    ci: bool = False,
    v: str | None = None,
):
    """Return the latest version and bad versions for a project.

    Query parameters
    ----------------
    ci : bool
        Whether the caller is running in CI.
    v : str | None
        The callers current version (recorded for telemetry).

    Backward compatibility: old clients send CI info as individual query
    params (name, isPR, etc.) instead of ``?ci=true``. Detect those.
    """
    # Backward compat: detect old-style CI params from ci_info.info()
    if not ci:
        old_ci_keys = {"name", "isPR", "isCI"}
        if old_ci_keys & set(request.query_params.keys()):
            ci = True

    # 1. Check allowlist
    allowlist: list[dict[str, str]] = getattr(request.app.state, "allowlist", [])
    allowed = any(
        e["owner"] == owner and e["repo"] == repo for e in allowlist
    )
    if not allowed:
        return JSONResponse(
            status_code=404,
            content={"error": "project not tracked"},
        )

    # 2. Look up project in DB
    stmt = select(Project).where(Project.owner == owner, Project.repo == repo)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None or not project.active:
        return JSONResponse(
            status_code=404,
            content={"error": "project not tracked"},
        )

    settings = request.app.state.settings

    # 3. Resolve geolocation (transient — IP is never stored)
    client_ip = request.client.host if request.client else "0.0.0.0"
    geolocator: GeoLocator | None = getattr(request.app.state, "geolocator", None)
    if geolocator is not None:
        geo_result = geolocator.resolve(client_ip)
    else:
        geo_result = _unknown_result()

    # 4. Record usage
    try:
        await record_usage(
            session=session,
            project_id=project.id,
            version=v or "unknown",
            geo_result=geo_result,
            is_ci=ci,
            time_bucket_hours=settings.TIME_BUCKET_HOURS,
        )
    except Exception:
        logger.warning("Failed to record usage for %s/%s", owner, repo, exc_info=True)

    # 5. Fetch version info
    try:
        http_client: httpx.AsyncClient = getattr(
            request.app.state, "http_client", None
        ) or httpx.AsyncClient()
        checker = VersionChecker(
            http_client=http_client,
            github_token=settings.GITHUB_TOKEN,
        )
        version_info = await checker.get_version_info(
            project, cache_ttl=settings.CACHE_TTL_SECONDS
        )
    except Exception:
        logger.warning(
            "Failed to get version info for %s/%s", owner, repo, exc_info=True
        )
        version_info = {"version": project.latest_version, "bad_versions": project.bad_versions or []}

    return {
        "version": version_info.get("version"),
        "bad_versions": version_info.get("bad_versions", []),
    }
