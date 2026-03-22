"""Tests for etelemetry_server.allowlist."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from etelemetry_server.allowlist import load_allowlist, sync_allowlist_to_db
from etelemetry_server.models import Project


class TestLoadAllowlist:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        data = [
            {"owner": "nipy", "repo": "nipype"},
            {"owner": "poldracklab", "repo": "fmriprep"},
        ]
        f = tmp_path / "allowlist.yml"
        f.write_text(yaml.dump(data))

        result = load_allowlist(str(f))
        assert len(result) == 2
        assert result[0] == {"owner": "nipy", "repo": "nipype"}
        assert result[1] == {"owner": "poldracklab", "repo": "fmriprep"}

    def test_load_nonexistent_file(self) -> None:
        result = load_allowlist("/nonexistent/path.yml")
        assert result == []

    def test_load_invalid_yaml_not_a_list(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yml"
        f.write_text("key: value")
        result = load_allowlist(str(f))
        assert result == []

    def test_load_skips_malformed_entries(self, tmp_path: Path) -> None:
        data = [
            {"owner": "nipy", "repo": "nipype"},
            {"something": "else"},
            "just a string",
        ]
        f = tmp_path / "allowlist.yml"
        f.write_text(yaml.dump(data))

        result = load_allowlist(str(f))
        assert len(result) == 1
        assert result[0] == {"owner": "nipy", "repo": "nipype"}

    def test_load_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yml"
        f.write_text("")
        result = load_allowlist(str(f))
        assert result == []


class TestSyncAllowlistToDb:
    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_inserts_new_projects(self, mock_session: AsyncMock) -> None:
        # No existing projects
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        entries = [{"owner": "nipy", "repo": "nipype"}]
        await sync_allowlist_to_db(mock_session, entries)

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, Project)
        assert added.owner == "nipy"
        assert added.repo == "nipype"
        assert added.active is True

    @pytest.mark.asyncio
    async def test_deactivates_removed_projects(
        self, mock_session: AsyncMock
    ) -> None:
        existing = Project(owner="old", repo="project")
        existing.active = True

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = result_mock

        # Empty allowlist — should deactivate existing
        await sync_allowlist_to_db(mock_session, [])

        assert existing.active is False

    @pytest.mark.asyncio
    async def test_reactivates_returning_projects(
        self, mock_session: AsyncMock
    ) -> None:
        existing = Project(owner="nipy", repo="nipype")
        existing.active = False

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = result_mock

        entries = [{"owner": "nipy", "repo": "nipype"}]
        await sync_allowlist_to_db(mock_session, entries)

        assert existing.active is True
        # Should not add a new project
        mock_session.add.assert_not_called()
