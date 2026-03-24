"""Unit tests for etelemetry.config URL resolution."""

from __future__ import annotations

import pytest

import etelemetry.config as config
from etelemetry.config import resolve_url


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Reset module-level default_url and env vars."""
    monkeypatch.delenv("NO_ET", raising=False)
    monkeypatch.delenv("ETELEMETRY_URL", raising=False)
    monkeypatch.setattr(config, "default_url", None)


class TestResolveUrl:
    def test_param_takes_highest_precedence(self, monkeypatch):
        monkeypatch.setenv("ETELEMETRY_URL", "https://env.example.com")
        monkeypatch.setattr(config, "default_url", "https://default.example.com")
        result = resolve_url(server_url="https://param.example.com")
        assert result == "https://param.example.com"

    def test_env_var_over_default_url(self, monkeypatch):
        monkeypatch.setenv("ETELEMETRY_URL", "https://env.example.com")
        monkeypatch.setattr(config, "default_url", "https://default.example.com")
        result = resolve_url()
        assert result == "https://env.example.com"

    def test_default_url_over_hardcoded(self, monkeypatch):
        monkeypatch.setattr(config, "default_url", "https://default.example.com")
        result = resolve_url()
        assert result == "https://default.example.com"

    def test_hardcoded_fallback(self):
        result = resolve_url()
        assert result == config._HARDCODED_URL

    def test_no_et_returns_none(self, monkeypatch):
        monkeypatch.setenv("NO_ET", "1")
        result = resolve_url(server_url="https://param.example.com")
        assert result is None

    def test_no_et_overrides_all(self, monkeypatch):
        monkeypatch.setenv("NO_ET", "1")
        monkeypatch.setenv("ETELEMETRY_URL", "https://env.example.com")
        monkeypatch.setattr(config, "default_url", "https://default.example.com")
        result = resolve_url(server_url="https://param.example.com")
        assert result is None

    def test_empty_server_url_falls_through(self, monkeypatch):
        monkeypatch.setenv("ETELEMETRY_URL", "https://env.example.com")
        result = resolve_url(server_url="")
        assert result == "https://env.example.com"

    def test_none_server_url_falls_through(self, monkeypatch):
        monkeypatch.setenv("ETELEMETRY_URL", "https://env.example.com")
        result = resolve_url(server_url=None)
        assert result == "https://env.example.com"
