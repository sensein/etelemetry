"""Integration tests for the dashboard.

Seeds DB with 12+ months of sample version_check data across
multiple projects/locations. Verifies HTML pages render and API
returns correct aggregated data. Uses SQLite in-memory.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from etelemetry_server.app import create_app
from etelemetry_server.db import get_db
from etelemetry_server.models import Base, Project, VersionCheck

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Sample data spanning 14 months
LOCATIONS = [
    {
        "city": "Cambridge",
        "region": "Massachusetts",
        "country": "United States",
        "country_code": "US",
        "latitude": 42.36,
        "longitude": -71.06,
    },
    {
        "city": "London",
        "region": "England",
        "country": "United Kingdom",
        "country_code": "GB",
        "latitude": 51.51,
        "longitude": -0.13,
    },
    {
        "city": "Berlin",
        "region": "Berlin",
        "country": "Germany",
        "country_code": "DE",
        "latitude": 52.52,
        "longitude": 13.40,
    },
    {
        "city": "Tokyo",
        "region": "Tokyo",
        "country": "Japan",
        "country_code": "JP",
        "latitude": 35.68,
        "longitude": 139.69,
    },
]

VERSIONS = ["1.8.0", "1.8.6", "1.9.0"]


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
    """Seed DB with 14 months of version check data across 2 projects and 4 locations."""
    async with session_factory() as session:
        p1 = Project(owner="nipy", repo="nipype", active=True)
        p2 = Project(owner="nipy", repo="nibabel", active=True)
        session.add_all([p1, p2])
        await session.flush()

        checks = []
        # Generate 14 months of data: Jan 2025 through Feb 2026
        start_date = datetime.date(2025, 1, 1)
        for month_offset in range(14):
            year = 2025 + (start_date.month + month_offset - 1) // 12
            month = (start_date.month + month_offset - 1) % 12 + 1
            bucket_time = datetime.datetime(year, month, 15, 12, 0, 0)

            for loc_idx, loc in enumerate(LOCATIONS):
                for ver_idx, version in enumerate(VERSIONS):
                    count_val = (month_offset + 1) * (loc_idx + 1) * (ver_idx + 1)
                    # Project 1
                    checks.append(
                        VersionCheck(
                            project_id=p1.id,
                            version=version,
                            city=loc["city"],
                            region=loc["region"],
                            country=loc["country"],
                            country_code=loc["country_code"],
                            latitude=loc["latitude"],
                            longitude=loc["longitude"],
                            is_ci=(ver_idx == 0),
                            time_bucket=bucket_time,
                            count=count_val,
                        )
                    )
                    # Project 2 (half the data)
                    if loc_idx < 2:
                        checks.append(
                            VersionCheck(
                                project_id=p2.id,
                                version=version,
                                city=loc["city"],
                                region=loc["region"],
                                country=loc["country"],
                                country_code=loc["country_code"],
                                latitude=loc["latitude"],
                                longitude=loc["longitude"],
                                is_ci=False,
                                time_bucket=bucket_time,
                                count=count_val // 2 + 1,
                            )
                        )

        session.add_all(checks)
        await session.commit()
        return {"p1": p1, "p2": p2}


@pytest.fixture
def app(session_factory, seed_data):
    """Build the FastAPI app wired to the test DB session."""
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


# ---------------------------------------------------------------------------
# HTML page tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dashboard_index_returns_html(app):
    """GET /dashboard/ returns 200 with HTML content."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "nipy/nipype" in resp.text
    assert "nipy/nibabel" in resp.text
    assert "<table" in resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dashboard_project_detail_returns_html(app):
    """GET /dashboard/project/{owner}/{repo} returns 200 with HTML."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/project/nipy/nipype")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "nipy/nipype" in resp.text
    assert "map" in resp.text
    assert "Version Distribution" in resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dashboard_project_detail_404_for_unknown(app):
    """GET /dashboard/project/{owner}/{repo} returns 404 for unknown project."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/project/unknown/repo")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API data tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_projects_returns_correct_data(app):
    """API returns both projects with non-zero check counts."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/api/projects")

    assert resp.status_code == 200
    body = resp.json()
    projects = body["projects"]
    assert len(projects) == 2

    # Verify projects are present with correct owners
    owners_repos = {(p["owner"], p["repo"]) for p in projects}
    assert ("nipy", "nipype") in owners_repos
    assert ("nipy", "nibabel") in owners_repos

    # All should have non-zero total_checks
    for p in projects:
        assert p["total_checks"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_stats_aggregated_data(app):
    """Stats API returns correctly aggregated data across 14 months."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={"from": "2025-01-01", "to": "2026-12-31"},
        )

    assert resp.status_code == 200
    body = resp.json()

    assert body["project"] == "nipy/nipype"
    assert body["total_checks"] > 0

    # Should have 3 versions
    assert len(body["by_version"]) == 3
    version_names = {v["version"] for v in body["by_version"]}
    assert version_names == {"1.8.0", "1.8.6", "1.9.0"}

    # Should have 4 locations
    assert len(body["by_location"]) == 4
    countries = {loc["country_code"] for loc in body["by_location"]}
    assert countries == {"US", "GB", "DE", "JP"}

    # Timeline should have entries
    assert len(body["timeline"]) > 0

    # Verify counts sum correctly
    version_total = sum(v["count"] for v in body["by_version"])
    assert version_total == body["total_checks"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_geo_returns_features(app):
    """GeoJSON API returns features with valid coordinates."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/geo/nipy/nipype",
            params={"from": "2025-01-01", "to": "2026-12-31"},
        )

    assert resp.status_code == 200
    body = resp.json()

    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 4  # 4 unique locations

    for feature in body["features"]:
        coords = feature["geometry"]["coordinates"]
        lon, lat = coords
        assert -180 <= lon <= 180
        assert -90 <= lat <= 90
        assert feature["properties"]["count"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_stats_date_filtering(app):
    """Stats API correctly filters by date range."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Query only January 2025
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={"from": "2025-01-01", "to": "2025-01-31"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_checks"] > 0

    # Query a range with no data
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={"from": "2020-01-01", "to": "2020-12-31"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_checks"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_stats_granularity_monthly(app):
    """Monthly granularity groups timeline data correctly."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/dashboard/api/stats/nipy/nipype",
            params={
                "from": "2025-01-01",
                "to": "2026-12-31",
                "granularity": "monthly",
            },
        )

    assert resp.status_code == 200
    body = resp.json()

    # With monthly granularity, we should have <=14 timeline entries
    assert len(body["timeline"]) <= 14
    for entry in body["timeline"]:
        # Monthly format: YYYY-MM
        assert len(entry["period"]) == 7
        assert "-" in entry["period"]
