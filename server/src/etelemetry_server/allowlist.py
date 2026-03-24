"""Allowlist loading, DB synchronisation, and SIGHUP reload handler."""

from __future__ import annotations

import logging
import signal
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from etelemetry_server.models import Project

logger = logging.getLogger(__name__)


def load_allowlist(path: str) -> list[dict[str, str]]:
    """Load a YAML allowlist file and return a list of {owner, repo} dicts.

    The YAML file is expected to contain a top-level list of mappings, e.g.:

        - owner: nipy
          repo: nipype
        - owner: poldracklab
          repo: fmriprep

    Returns an empty list when the file does not exist.
    """
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Allowlist file not found: %s", path)
        return []

    with filepath.open() as fh:
        data: Any = yaml.safe_load(fh)

    if not isinstance(data, list):
        logger.warning("Allowlist is not a list; returning empty")
        return []

    entries: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and "owner" in item and "repo" in item:
            entries.append({"owner": str(item["owner"]), "repo": str(item["repo"])})
    return entries


async def sync_allowlist_to_db(
    session: AsyncSession, entries: list[dict[str, str]]
) -> None:
    """Synchronise allowlist entries with the projects table.

    * Inserts projects that are in the allowlist but not yet in the DB.
    * Deactivates projects that are in the DB but no longer in the allowlist.
    * Re-activates projects that reappear in the allowlist.
    """
    allowlist_set = {(e["owner"], e["repo"]) for e in entries}

    result = await session.execute(select(Project))
    existing_projects: list[Project] = list(result.scalars().all())

    existing_map: dict[tuple[str, str], Project] = {
        (p.owner, p.repo): p for p in existing_projects
    }

    # Insert missing projects
    for owner, repo in allowlist_set:
        if (owner, repo) not in existing_map:
            session.add(Project(owner=owner, repo=repo, active=True))
        else:
            project = existing_map[(owner, repo)]
            if not project.active:
                project.active = True

    # Deactivate removed projects
    for key, project in existing_map.items():
        if key not in allowlist_set and project.active:
            project.active = False

    await session.flush()


def setup_sighup_handler(path: str, callback: Callable[[], Any]) -> None:
    """Register a SIGHUP handler that reloads the allowlist.

    Parameters
    ----------
    path : str
        Path to the allowlist YAML file (for logging purposes).
    callback : callable
        Function to invoke when SIGHUP is received (typically reloads
        the allowlist and syncs to DB).
    """

    def _handler(signum: int, frame: Any) -> None:
        logger.info("SIGHUP received — reloading allowlist from %s", path)
        callback()

    signal.signal(signal.SIGHUP, _handler)
