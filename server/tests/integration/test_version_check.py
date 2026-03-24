"""Integration tests for the version-check flow.

These tests exercise the full request path with a real (test) database.
Mark with ``pytest.mark.integration`` so they can be selected/skipped via
``pytest -m integration``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from etelemetry_server.app import create_app
from etelemetry_server.models import Base, Project, VersionCheck

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
async def seed_project(session_factory):
    """Seed a test project in the DB and return it."""
    async with session_factory() as session:
        project = Project(owner="testorg", repo="testrepo", active=True)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


@pytest.fixture
def app(session_factory, seed_project):
    """Build the FastAPI app wired to the test DB session."""
    application = create_app()

    application.state.allowlist = [
        {"owner": "testorg", "repo": "testrepo"},
    ]
    application.state.settings = MagicMock(
        GITHUB_TOKEN=None,
        CACHE_TTL_SECONDS=3600,
        TIME_BUCKET_HOURS=1,
        MAXMIND_DB_PATH="/nonexistent",
    )
    application.state.geolocator = None
    application.state.http_client = httpx.AsyncClient()

    # Override the get_db dependency to use our test session factory
    from etelemetry_server.db import get_db

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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_version_check_records_geo_no_ip(app, session_factory, seed_project):
    """A version-check request stores geolocation but never stores IP."""
    with patch(
        "etelemetry_server.routes.projects.VersionChecker"
    ) as MockChecker:
        instance = MockChecker.return_value
        instance.get_version_info = AsyncMock(
            return_value={"version": "2.0.0", "bad_versions": []}
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/projects/testorg/testrepo", params={"v": "1.0.0"}
            )

        assert resp.status_code == 200

    # Verify DB record
    async with session_factory() as session:
        result = await session.execute(select(VersionCheck))
        records = list(result.scalars().all())

    assert len(records) >= 1
    record = records[0]

    # Geolocation fields present
    assert hasattr(record, "city")
    assert hasattr(record, "region")
    assert hasattr(record, "country")
    assert hasattr(record, "country_code")
    assert hasattr(record, "latitude")
    assert hasattr(record, "longitude")

    # No IP column on the model
    assert not hasattr(record, "ip")
    assert not hasattr(record, "ip_address")

    # Check recorded values
    assert record.project_id == seed_project.id
    assert record.version == "1.0.0"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_version_check_response_shape(app, session_factory, seed_project):
    """The endpoint returns the correct JSON shape."""
    with patch(
        "etelemetry_server.routes.projects.VersionChecker"
    ) as MockChecker:
        instance = MockChecker.return_value
        instance.get_version_info = AsyncMock(
            return_value={"version": "2.0.0", "bad_versions": ["0.9.0"]}
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/testorg/testrepo")

    body = resp.json()
    assert body["version"] == "2.0.0"
    assert body["bad_versions"] == ["0.9.0"]
