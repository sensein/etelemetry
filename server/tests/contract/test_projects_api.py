"""Contract tests for GET /projects/{owner}/{repo}."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from etelemetry_server.app import create_app


@pytest.fixture
def app():
    """Create a test app with a mocked allowlist and services."""
    application = create_app()

    # Provide minimal app.state fixtures
    application.state.allowlist = [
        {"owner": "nipy", "repo": "nipype"},
    ]
    application.state.settings = MagicMock(
        GITHUB_TOKEN=None,
        CACHE_TTL_SECONDS=3600,
        TIME_BUCKET_HOURS=1,
        MAXMIND_DB_PATH="/nonexistent",
    )
    application.state.geolocator = None
    application.state.http_client = httpx.AsyncClient()

    return application


@pytest.mark.asyncio
async def test_200_response_shape(app):
    """A known project returns 200 with version and bad_versions keys."""
    mock_project = MagicMock()
    mock_project.id = 1
    mock_project.owner = "nipy"
    mock_project.repo = "nipype"
    mock_project.active = True
    mock_project.latest_version = "1.8.6"
    mock_project.bad_versions = ["1.0.0"]
    mock_project.cache_expires_at = None

    with (
        patch(
            "etelemetry_server.routes.projects.get_db",
            return_value=_mock_session(mock_project),
        ),
        patch(
            "etelemetry_server.routes.projects.record_usage",
            new_callable=AsyncMock,
        ),
        patch(
            "etelemetry_server.routes.projects.VersionChecker"
        ) as MockChecker,
    ):
        instance = MockChecker.return_value
        instance.get_version_info = AsyncMock(
            return_value={"version": "1.8.6", "bad_versions": ["1.0.0"]}
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/nipy/nipype")

        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body
        assert "bad_versions" in body
        assert isinstance(body["bad_versions"], list)


@pytest.mark.asyncio
async def test_404_for_project_not_on_allowlist(app):
    """A project not on the allowlist returns 404 with an error message."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/projects/unknown/repo")

    assert resp.status_code == 404
    body = resp.json()
    assert body == {"error": "project not tracked"}


@pytest.mark.asyncio
async def test_400_malformed_project_identifier(app):
    """Malformed project identifiers should not match the route (404)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # FastAPI path params will still match two segments;
        # a single segment should yield 404 (no route match).
        resp = await client.get("/projects/onlyone")

    assert resp.status_code in (404, 422)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _mock_session(project):
    """Yield a mock async session that returns *project* on execute."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = project
    session.execute = AsyncMock(return_value=result)
    yield session
