"""Tests for etelemetry_server.settings."""

import os
from unittest.mock import patch

from etelemetry_server.settings import Settings


class TestSettingsDefaults:
    """Verify default values when no environment variables are set."""

    def test_default_database_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.DATABASE_URL == "postgresql+asyncpg://localhost:5432/etelemetry"

    def test_default_maxmind_db_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.MAXMIND_DB_PATH == "/data/GeoLite2-City.mmdb"

    def test_default_github_token_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.GITHUB_TOKEN is None

    def test_default_cache_ttl(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.CACHE_TTL_SECONDS == 21600

    def test_default_allowlist_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.ALLOWLIST_PATH == "allowlist.yml"

    def test_default_time_bucket_hours(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.TIME_BUCKET_HOURS == 1

    def test_default_server_host(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.SERVER_HOST == "0.0.0.0"

    def test_default_server_port(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings()
        assert s.SERVER_PORT == 8000


class TestSettingsFromEnv:
    """Verify settings are loaded from environment variables."""

    def test_database_url_from_env(self) -> None:
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql+asyncpg://db:5432/test"}
        ):
            s = Settings()
        assert s.DATABASE_URL == "postgresql+asyncpg://db:5432/test"

    def test_github_token_from_env(self) -> None:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_abc123"}):
            s = Settings()
        assert s.GITHUB_TOKEN == "ghp_abc123"

    def test_cache_ttl_from_env(self) -> None:
        with patch.dict(os.environ, {"CACHE_TTL_SECONDS": "3600"}):
            s = Settings()
        assert s.CACHE_TTL_SECONDS == 3600

    def test_server_port_from_env(self) -> None:
        with patch.dict(os.environ, {"SERVER_PORT": "9000"}):
            s = Settings()
        assert s.SERVER_PORT == 9000

    def test_time_bucket_hours_from_env(self) -> None:
        with patch.dict(os.environ, {"TIME_BUCKET_HOURS": "6"}):
            s = Settings()
        assert s.TIME_BUCKET_HOURS == 6
