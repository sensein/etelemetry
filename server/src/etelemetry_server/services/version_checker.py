"""Version checker service — fetches latest version info from GitHub."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from etelemetry_server.models import Project

logger = logging.getLogger(__name__)


class VersionChecker:
    """Fetch and cache latest version information for a project."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        github_token: str | None = None,
    ) -> None:
        self._http = http_client
        self._github_token = github_token
        # In-memory LRU / TTL-aware cache keyed by "owner/repo"
        self._memory_cache: dict[str, dict] = {}
        self._cache_ts: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_version_info(
        self, project: Project, cache_ttl: int
    ) -> dict:
        """Return ``{"version": ..., "bad_versions": [...]}`` for *project*.

        Uses the project's DB-level cache first, then falls back to GitHub,
        and keeps an in-memory cache as a last resort.
        """
        key = f"{project.owner}/{project.repo}"

        # 1. DB-level cache
        now = datetime.now(timezone.utc)
        if project.cache_expires_at and project.cache_expires_at > now:
            result = {
                "version": project.latest_version,
                "bad_versions": project.bad_versions or [],
            }
            self._set_mem_cache(key, result, cache_ttl)
            return result

        # 2. Fetch from GitHub
        try:
            version = await self._fetch_latest_version(project.owner, project.repo)
            bad_versions = await self._fetch_bad_versions(project.owner, project.repo)

            # Update project record (caller is expected to commit)
            project.latest_version = version
            project.bad_versions = bad_versions
            from datetime import timedelta

            project.cache_expires_at = now + timedelta(seconds=cache_ttl)

            result = {"version": version, "bad_versions": bad_versions}
            self._set_mem_cache(key, result, cache_ttl)
            return result

        except _RateLimitedError:
            logger.warning("GitHub rate-limited; returning stale data for %s", key)
            return self._stale_or_empty(project, key)

        except Exception:
            logger.warning(
                "Failed to fetch version info for %s", key, exc_info=True
            )
            return self._stale_or_empty(project, key)

    # ------------------------------------------------------------------
    # In-memory cache helpers (T018)
    # ------------------------------------------------------------------

    def _set_mem_cache(self, key: str, value: dict, ttl: int) -> None:
        self._memory_cache[key] = value
        self._cache_ts[key] = time.monotonic() + ttl

    def _get_mem_cache(self, key: str) -> dict | None:
        if key in self._memory_cache:
            # Return even if expired — it is stale but better than nothing
            return self._memory_cache[key]
        return None

    def _stale_or_empty(self, project: Project, key: str) -> dict:
        """Return the best available stale data, or an empty result."""
        # Try in-memory cache first
        cached = self._get_mem_cache(key)
        if cached is not None:
            return cached
        # Fall back to whatever the DB has
        if project.latest_version:
            return {
                "version": project.latest_version,
                "bad_versions": project.bad_versions or [],
            }
        return {"version": None, "bad_versions": []}

    # ------------------------------------------------------------------
    # GitHub fetching internals
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        return headers

    async def _fetch_latest_version(self, owner: str, repo: str) -> str | None:
        """Try releases/latest, then fall back to tags."""
        headers = self._auth_headers()

        # Try releases endpoint
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        resp = await self._http.get(url, headers=headers)

        if resp.status_code == 403:
            raise _RateLimitedError()

        if resp.status_code == 200:
            tag = resp.json().get("tag_name", "")
            return tag.lstrip("v") if tag else None

        # Fallback to tags
        if resp.status_code == 404:
            tags_url = f"https://api.github.com/repos/{owner}/{repo}/tags"
            resp = await self._http.get(tags_url, headers=headers)
            if resp.status_code == 403:
                raise _RateLimitedError()
            if resp.status_code == 200:
                tags = resp.json()
                if tags:
                    tag = tags[0].get("name", "")
                    return tag.lstrip("v") if tag else None

        return None

    async def _fetch_bad_versions(self, owner: str, repo: str) -> list[str]:
        """Fetch the ``.et`` file from the repository root."""
        headers = self._auth_headers()
        # Try master then main
        for branch in ("master", "main"):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/.et"
            resp = await self._http.get(url, headers=headers)
            if resp.status_code == 200:
                try:
                    import json

                    data = json.loads(resp.text)
                    return data.get("bad_versions", [])
                except Exception:
                    logger.debug("Failed to parse .et for %s/%s", owner, repo)
                    return []
        return []


class _RateLimitedError(Exception):
    """Raised when GitHub returns a 403 rate-limit response."""
