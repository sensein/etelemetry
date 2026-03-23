"""End-to-end integration test: real client library talking to real server.

Uses httpx ASGITransport to connect the etelemetry client library to the
FastAPI server without needing a real TCP socket. The client's HTTP call
is intercepted and routed through the ASGI app in-process.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from etelemetry_server.app import create_app
from etelemetry_server.models import Base, Project
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    async with session_factory() as session:
        project = Project(
            owner="testorg",
            repo="testrepo",
            active=True,
            latest_version="3.0.0",
            bad_versions=["1.0.0"],
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


@pytest.fixture
def app(session_factory, seed_project):
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


def _make_asgi_request(app, method, url, **kwargs):
    """Route a requests-style call through the ASGI app in-process.

    This replaces the real HTTP call that ``etelemetry.client._etrequest``
    would make, routing it through the FastAPI app via httpx ASGITransport.
    """
    import asyncio

    # Extract just the path + query from the URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"

    # Merge any extra params into the query string
    params = kwargs.pop("params", {})

    async def _do_request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.request(method, path, params=params, **kwargs)
        return resp

    resp = asyncio.get_event_loop().run_until_complete(_do_request())

    # Wrap in a requests-like response object
    mock_resp = MagicMock()
    mock_resp.status_code = resp.status_code
    mock_resp.json.return_value = resp.json()
    mock_resp.raise_for_status.side_effect = (
        None if resp.is_success else Exception(f"HTTP {resp.status_code}")
    )
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClientServerE2E:
    """Full round-trip: etelemetry client library → FastAPI server → DB."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        import etelemetry.client
        etelemetry.client._available_version_checked = None
        yield
        etelemetry.client._available_version_checked = None

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("NO_ET", raising=False)
        monkeypatch.delenv("ETELEMETRY_URL", raising=False)

    def _patch_requests(self, app):
        """Patch requests.request to route through the ASGI app."""
        import functools
        return patch(
            "requests.request",
            side_effect=functools.partial(_make_asgi_request, app),
        )

    def test_get_project_returns_version(self, app):
        """Client get_project() returns version info from the server."""
        with (
            self._patch_requests(app),
            patch(
                "etelemetry_server.services.version_checker.VersionChecker.get_version_info",
                new_callable=AsyncMock,
                return_value={"version": "3.0.0", "bad_versions": ["1.0.0"]},
            ),
        ):
            import etelemetry
            result = etelemetry.get_project(
                "testorg/testrepo",
                server_url="http://testserver",
            )

        assert result is not None
        assert result["version"] == "3.0.0"
        assert result["bad_versions"] == ["1.0.0"]

    def test_check_available_version_warns_outdated(self, app, caplog):
        """Client warns when local version is behind server version."""
        with (
            self._patch_requests(app),
            patch(
                "etelemetry_server.services.version_checker.VersionChecker.get_version_info",
                new_callable=AsyncMock,
                return_value={"version": "3.0.0", "bad_versions": []},
            ),
            caplog.at_level(logging.WARNING, logger="et-client"),
        ):
            import etelemetry
            result = etelemetry.check_available_version(
                "testorg/testrepo",
                "2.0.0",
                server_url="http://testserver",
            )

        assert result is not None
        assert result["version"] == "3.0.0"
        assert "newer version" in caplog.text.lower()

    def test_check_available_version_detects_bad_version(self, app):
        """Client raises BadVersionError for known bad versions."""
        with (
            self._patch_requests(app),
            patch(
                "etelemetry_server.services.version_checker.VersionChecker.get_version_info",
                new_callable=AsyncMock,
                return_value={"version": "3.0.0", "bad_versions": ["1.0.0"]},
            ),
        ):
            import etelemetry
            with pytest.raises(etelemetry.BadVersionError, match="critical bug"):
                etelemetry.check_available_version(
                    "testorg/testrepo",
                    "1.0.0",
                    raise_exception=True,
                    server_url="http://testserver",
                )

    def test_project_not_on_allowlist_returns_error(self, app):
        """Client gets an error for projects not on the allowlist."""
        with self._patch_requests(app):
            import etelemetry
            with pytest.raises(Exception):
                etelemetry.get_project(
                    "unknown/repo",
                    server_url="http://testserver",
                )

    def test_response_shape_matches_old_client_expectations(self, app):
        """Response has 'version' and 'bad_versions' keys — backward compat."""
        with (
            self._patch_requests(app),
            patch(
                "etelemetry_server.services.version_checker.VersionChecker.get_version_info",
                new_callable=AsyncMock,
                return_value={"version": "3.0.0", "bad_versions": ["1.0.0"]},
            ),
        ):
            import etelemetry
            result = etelemetry.get_project(
                "testorg/testrepo",
                server_url="http://testserver",
            )

        # These are the exact keys the old client reads
        assert "version" in result
        assert "bad_versions" in result
        # Should NOT have internal-only keys
        assert "status" not in result
        assert "last_update" not in result
        assert "cached" not in result
