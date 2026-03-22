"""Unit tests for etelemetry client."""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

import etelemetry
from etelemetry.client import _available_version_checked, check_available_version, get_project
from etelemetry.errors import BadVersionError


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the global version check cache before each test."""
    import etelemetry.client
    etelemetry.client._available_version_checked = None
    yield
    etelemetry.client._available_version_checked = None


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure NO_ET and ETELEMETRY_URL are not set."""
    monkeypatch.delenv("NO_ET", raising=False)
    monkeypatch.delenv("ETELEMETRY_URL", raising=False)


class TestGetProject:
    def test_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("NO_ET", "1")
        assert get_project("owner/repo") is None

    def test_raises_on_invalid_repo(self):
        with pytest.raises(ValueError, match="Invalid repository"):
            get_project("no-slash-here")

    @patch("etelemetry.client._etrequest")
    def test_returns_version_info(self, mock_req):
        mock_req.return_value = {"version": "1.0.0", "bad_versions": []}
        result = get_project("owner/repo")
        assert result["version"] == "1.0.0"
        assert result["bad_versions"] == []

    @patch("etelemetry.client._etrequest")
    def test_uses_custom_env_url(self, mock_req, monkeypatch):
        monkeypatch.setenv("ETELEMETRY_URL", "https://custom.example.com")
        mock_req.return_value = {"version": "1.0.0", "bad_versions": []}
        get_project("owner/repo")
        call_args = mock_req.call_args
        assert "custom.example.com" in call_args[0][0]


class TestCheckAvailableVersion:
    @patch("etelemetry.client.get_project")
    def test_warns_on_outdated_version(self, mock_gp, caplog):
        mock_gp.return_value = {"version": "2.0.0", "bad_versions": []}
        with caplog.at_level(logging.WARNING, logger="et-client"):
            result = check_available_version("owner/repo", "1.0.0")
        assert result["version"] == "2.0.0"
        assert "newer version" in caplog.text.lower()

    @patch("etelemetry.client.get_project")
    def test_critical_on_bad_version(self, mock_gp, caplog):
        mock_gp.return_value = {"version": "2.0.0", "bad_versions": ["1.0.0"]}
        with caplog.at_level(logging.CRITICAL, logger="et-client"):
            result = check_available_version("owner/repo", "1.0.0")
        assert "critical bug" in caplog.text.lower()

    @patch("etelemetry.client.get_project")
    def test_raises_bad_version_error(self, mock_gp):
        mock_gp.return_value = {"version": "2.0.0", "bad_versions": ["1.0.0"]}
        with pytest.raises(BadVersionError, match="critical bug"):
            check_available_version(
                "owner/repo", "1.0.0", raise_exception=True
            )

    @patch("etelemetry.client.get_project")
    def test_debug_on_latest_version(self, mock_gp, caplog):
        mock_gp.return_value = {"version": "1.0.0", "bad_versions": []}
        with caplog.at_level(logging.DEBUG, logger="et-client"):
            result = check_available_version("owner/repo", "1.0.0")
        assert result["version"] == "1.0.0"

    @patch("etelemetry.client.get_project")
    def test_caches_result(self, mock_gp):
        mock_gp.return_value = {"version": "2.0.0", "bad_versions": []}
        result1 = check_available_version("owner/repo", "1.0.0")
        result2 = check_available_version("owner/repo", "1.0.0")
        assert result1 is result2
        mock_gp.assert_called_once()

    @patch("etelemetry.client.get_project")
    def test_returns_none_on_connection_error(self, mock_gp):
        mock_gp.side_effect = RuntimeError("Connection failed")
        result = check_available_version("owner/repo", "1.0.0")
        assert result is None

    def test_no_et_disables_get_project(self, monkeypatch):
        monkeypatch.setenv("NO_ET", "1")
        result = get_project("owner/repo")
        assert result is None


class TestPublicAPI:
    def test_exports_get_project(self):
        assert hasattr(etelemetry, "get_project")

    def test_exports_check_available_version(self):
        assert hasattr(etelemetry, "check_available_version")

    def test_exports_bad_version_error(self):
        assert hasattr(etelemetry, "BadVersionError")
        assert issubclass(etelemetry.BadVersionError, RuntimeError)

    def test_exports_version(self):
        assert hasattr(etelemetry, "__version__")
