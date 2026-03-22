"""Contract tests for dashboard API endpoints.

Verify response shapes match contracts/api.md exactly.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from etelemetry_server.app import create_app
from etelemetry_server.db import get_db
from etelemetry_server.models import Base, Project, VersionCheck

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_data(session_factory):
    """Seed DB with test projects and version checks."""
    async with session_factory() as session:
        p1 = Project(owner="nipy", repo="nipype", active=True)
        p2 = Project(owner="nipy", repo="nibabel", active=True)
        session.add_all([p1, p2])
        await session.flush()

        now = datetime.datetime(2026, 3, 1, 12, 0, 0)
        checks = [
            VersionCheck(
                project_id=p1.id,
                version="1.8.6",
                city="Cambridge",
                region="Massachusetts",
                country="United States",
                country_code="US",
                latitude=42.36,
                longitude=-71.06,
                is_ci=False,
                time_bucket=now,
                count=100,
            ),
            VersionCheck(
                project_id=p1.id,
                version="1.9.0",
                city="London",
                region="England",
                country="United Kingdom",
                country_code="GB",
                latitude=51.51,
                longitude=-0.13,
                is_ci=True,
                time_bucket=now,
                count=50,
            ),
            VersionCheck(
                project_id=p2.id,
                version="4.0.0",
                city="Berlin",
                region="Berlin",
                country="Germany",
                country_code="DE",
                latitude=52.52,
                longitude=13.40,
                is_ci=False,
                time_bucket=now,
                count=75,
            ),
        ]
        session.add_all(checks)
        await session.commit()
        return {"p1": p1, "p2": p2}


@pytest.fixture
def app(session_factory, seed_data):
    """Build FastAPI app wired to test DB."""
    application = create_app()
    application.state.allowlist = [
        {"owner": "nipy", "repo": "nipype"},
        {"owner": "nipy", "repo": "nibabel"},
    ]
    application.state.settings = MagicMock(
        GITHUB_TOKEN=None,
        CACHE_TTL_SECONDS=3600,
        TIME_BUCKET_HOURS=1,
        MAXMIND_DB_PATH="/nonexistent",
    )
    application.state.geolocator = None
    application.state.http_client = httpx.AsyncClient()

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest.mark.asyncio
async def test_api_projects_response_shape(app):
    """GET /dashboard/api/projects returns list of projects with counts."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/api/projects")

    assert resp.status_code == 200
    body = resp.json()

    # Must have "projects" key containing a list
    assert "projects" in body
    assert isinstance(body["projects"], list)
    assert len(body["projects"]) >= 2

    # Each project must have owner, repo, total_checks
    for project in body["projects"]:
        assert "owner" in project
        assert "repo" in project
        assert "total_checks" in project
        assert isinstance(project["total_checks"], int)


@pytest.mark.asyncio
async def test_api_stats_response_shape(app):
    """GET /dashboard/api/stats/{owner}/{repo} returns stats with
    by_version, by_location, timeline.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )

    assert resp.status_code == 200
    body = resp.json()

    # Required top-level keys
    assert body["project"] == "nipy/nipype"
    assert "period" in body
    assert "from" in body["period"]
    assert "to" in body["period"]
    assert "total_checks" in body
    assert isinstance(body["total_checks"], int)
    assert body["total_checks"] > 0

    # by_version
    assert "by_version" in body
    assert isinstance(body["by_version"], list)
    for entry in body["by_version"]:
        assert "version" in entry
        assert "count" in entry
        assert isinstance(entry["count"], int)

    # by_location
    assert "by_location" in body
    assert isinstance(body["by_location"], list)
    for entry in body["by_location"]:
        assert "country" in entry
        assert "country_code" in entry
        assert "region" in entry
        assert "city" in entry
        assert "lat" in entry
        assert "lon" in entry
        assert "count" in entry

    # timeline
    assert "timeline" in body
    assert isinstance(body["timeline"], list)
    for entry in body["timeline"]:
        assert "period" in entry
        assert "count" in entry


@pytest.mark.asyncio
async def test_api_stats_404_for_unknown_project(app):
    """GET /dashboard/api/stats for unknown project returns 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/api/stats/unknown/repo")

    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_api_geo_response_shape(app):
    """GET /dashboard/api/geo/{owner}/{repo} returns GeoJSON FeatureCollection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/geo/nipy/nipype",
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )

    assert resp.status_code == 200
    body = resp.json()

    # Must be a GeoJSON FeatureCollection
    assert body["type"] == "FeatureCollection"
    assert "features" in body
    assert isinstance(body["features"], list)
    assert len(body["features"]) > 0

    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert feature["geometry"]["type"] == "Point"
        assert "coordinates" in feature["geometry"]
        coords = feature["geometry"]["coordinates"]
        assert len(coords) == 2  # [lon, lat]
        assert isinstance(coords[0], (int, float))
        assert isinstance(coords[1], (int, float))

        assert "properties" in feature
        assert "count" in feature["properties"]
        assert isinstance(feature["properties"]["count"], int)


@pytest.mark.asyncio
async def test_api_geo_404_for_unknown_project(app):
    """GET /dashboard/api/geo for unknown project returns 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/api/geo/unknown/repo")

    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_api_stats_granularity_param(app):
    """Stats endpoint respects granularity query parameter."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={
                "from": "2026-01-01",
                "to": "2026-12-31",
                "granularity": "monthly",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    # Timeline entries should use monthly format (YYYY-MM)
    for entry in body["timeline"]:
        assert len(entry["period"]) == 7  # e.g., "2026-03"
