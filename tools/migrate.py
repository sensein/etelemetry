"""MongoDB-to-PostgreSQL migration tool for etelemetry.

Reads the legacy ``et`` MongoDB database (``requests`` and ``geo``
collections) and inserts deduplicated records into the new PostgreSQL
schema.  IP addresses are never transferred.

Usage::

    python -m tools.migrate \
        --mongo-uri mongodb://localhost:27017 \
        --pg-uri postgresql://user:pass@localhost/etelemetry \
        --batch-size 1000 \
        --verify
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# Ensure the server package is importable when running from the repo root.
sys.path.insert(0, "server/src")

from etelemetry_server.models import Base, Project, VersionCheck  # noqa: E402

logger = logging.getLogger("tools.migrate")

# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------

_REQUIRED_REQUEST_FIELDS = {"owner", "repository", "version", "access_time"}


def _is_valid_request(doc: dict[str, Any]) -> bool:
    """Return True if the document has all required fields."""
    return _REQUIRED_REQUEST_FIELDS.issubset(doc.keys())


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _truncate_to_hour(dt: datetime.datetime) -> datetime.datetime:
    """Truncate a datetime to the start of its hour (UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def _parse_access_time(value: Any) -> datetime.datetime:
    """Parse an access_time value from MongoDB.

    Handles both datetime objects (as returned by pymongo) and ISO-format
    strings (as found in test fixtures).
    """
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value
    # String fallback
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(raw)


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------


def _build_geo_lookup(mongo_client: Any) -> dict[str, dict[str, Any]]:
    """Build a lookup dict from remote_addr -> geo fields."""
    db = mongo_client["et"]
    geo_lookup: dict[str, dict[str, Any]] = {}
    for doc in db["geo"].find():
        addr = doc.get("remote_addr")
        if addr:
            geo_lookup[addr] = {
                "city": doc.get("city", "unknown"),
                "region": doc.get("region_name", "unknown"),
                "country": doc.get("country_name", "unknown"),
                "latitude": doc.get("latitude"),
                "longitude": doc.get("longitude"),
            }
    return geo_lookup


_DEFAULT_GEO = {
    "city": "unknown",
    "region": "unknown",
    "country": "unknown",
    "latitude": None,
    "longitude": None,
}


def migrate_records(
    mongo_client: Any,
    pg_engine: Any,
    batch_size: int = 1000,
) -> dict[str, int]:
    """Migrate records from MongoDB to PostgreSQL.

    Parameters
    ----------
    mongo_client
        A ``pymongo.MongoClient`` (or mock) connected to the legacy database.
    pg_engine
        A SQLAlchemy engine connected to the target PostgreSQL database.
    batch_size
        Number of records to process before logging progress.

    Returns
    -------
    dict
        Statistics: ``imported``, ``skipped``, ``projects_created``.
    """
    Base.metadata.create_all(pg_engine)

    geo_lookup = _build_geo_lookup(mongo_client)
    db = mongo_client["et"]

    stats = {"imported": 0, "skipped": 0, "projects_created": 0}

    # Cache project_id lookups: (owner, repo) -> project.id
    project_cache: dict[tuple[str, str], int] = {}

    batch: list[dict[str, Any]] = []
    processed = 0

    for doc in db["requests"].find():
        if not _is_valid_request(doc):
            doc_id = doc.get("_id", "<unknown>")
            logger.warning("Skipping malformed record %s: missing required fields", doc_id)
            stats["skipped"] += 1
            continue

        try:
            access_time = _parse_access_time(doc["access_time"])
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping record %s: bad access_time: %s", doc.get("_id"), exc)
            stats["skipped"] += 1
            continue

        remote_addr = doc.get("remote_addr", "")
        geo = geo_lookup.get(remote_addr, _DEFAULT_GEO)

        batch.append(
            {
                "owner": doc["owner"],
                "repo": doc["repository"],
                "version": doc["version"],
                "is_ci": bool(doc.get("is_ci", False)),
                "time_bucket": _truncate_to_hour(access_time),
                "city": geo["city"],
                "region": geo["region"],
                "country": geo["country"],
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
            }
        )

        if len(batch) >= batch_size:
            _flush_batch(batch, pg_engine, project_cache, stats)
            batch = []
            processed += batch_size
            logger.info("Processed %d records so far ...", processed)

    # Flush remaining
    if batch:
        _flush_batch(batch, pg_engine, project_cache, stats)
        processed += len(batch)
        logger.info("Processed %d records (final batch).", processed)

    logger.info(
        "Migration complete: imported=%d  skipped=%d  projects_created=%d",
        stats["imported"],
        stats["skipped"],
        stats["projects_created"],
    )
    return stats


def _flush_batch(
    batch: list[dict[str, Any]],
    engine: Any,
    project_cache: dict[tuple[str, str], int],
    stats: dict[str, int],
) -> None:
    """Write a batch of mapped records into PostgreSQL."""
    with Session(engine) as session:
        for rec in batch:
            project_key = (rec["owner"], rec["repo"])

            # Ensure project exists
            if project_key not in project_cache:
                project = session.execute(
                    select(Project).where(
                        Project.owner == rec["owner"],
                        Project.repo == rec["repo"],
                    )
                ).scalar_one_or_none()

                if project is None:
                    project = Project(owner=rec["owner"], repo=rec["repo"])
                    session.add(project)
                    session.flush()
                    stats["projects_created"] += 1

                project_cache[project_key] = project.id

            project_id = project_cache[project_key]

            # Upsert version_check (content-addressed dedup)
            existing = session.execute(
                select(VersionCheck).where(
                    VersionCheck.project_id == project_id,
                    VersionCheck.version == rec["version"],
                    VersionCheck.city == rec["city"],
                    VersionCheck.region == rec["region"],
                    VersionCheck.is_ci == rec["is_ci"],
                    VersionCheck.time_bucket == rec["time_bucket"],
                )
            ).scalar_one_or_none()

            if existing is not None:
                existing.count += 1
            else:
                vc = VersionCheck(
                    project_id=project_id,
                    version=rec["version"],
                    city=rec["city"],
                    region=rec["region"],
                    country=rec["country"],
                    latitude=rec["latitude"],
                    longitude=rec["longitude"],
                    is_ci=rec["is_ci"],
                    time_bucket=rec["time_bucket"],
                    count=1,
                )
                session.add(vc)
                stats["imported"] += 1

        session.commit()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_migration(
    mongo_client: Any,
    pg_engine: Any,
) -> dict[str, int]:
    """Compare record counts between MongoDB and PostgreSQL.

    Returns
    -------
    dict
        ``mongo_requests``: total documents in MongoDB ``requests`` collection.
        ``pg_version_checks``: number of rows in ``version_checks``.
        ``pg_total_count``: sum of ``count`` across all ``version_checks`` rows.
    """
    db = mongo_client["et"]
    mongo_count = db["requests"].count_documents({})

    with Session(pg_engine) as session:
        pg_rows = session.execute(
            select(func.count(VersionCheck.id))
        ).scalar_one()
        pg_total = session.execute(
            select(func.coalesce(func.sum(VersionCheck.count), 0))
        ).scalar_one()

    result = {
        "mongo_requests": mongo_count,
        "pg_version_checks": pg_rows,
        "pg_total_count": pg_total,
    }

    logger.info("Verification results: %s", result)
    if mongo_count != pg_total:
        logger.warning(
            "Count mismatch: MongoDB has %d requests, PostgreSQL has %d total count "
            "(difference may be due to skipped malformed records).",
            mongo_count,
            pg_total,
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate etelemetry data from MongoDB to PostgreSQL.",
    )
    parser.add_argument(
        "--mongo-uri",
        required=True,
        help="MongoDB connection URI (e.g. mongodb://localhost:27017).",
    )
    parser.add_argument(
        "--pg-uri",
        required=True,
        help="PostgreSQL connection URI (e.g. postgresql://user:pass@localhost/etelemetry).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records per batch (default: 1000).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="After migration, compare record counts between MongoDB and PostgreSQL.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    # Late import so the CLI can be tested without pymongo installed.
    import pymongo  # noqa: F401 -- ensures pymongo is available

    mongo_client = pymongo.MongoClient(args.mongo_uri)
    pg_engine = create_engine(args.pg_uri)

    logger.info("Starting migration from %s to PostgreSQL ...", args.mongo_uri)

    stats = migrate_records(mongo_client, pg_engine, batch_size=args.batch_size)

    if args.verify:
        verify_migration(mongo_client, pg_engine)

    logger.info("Done. Stats: %s", stats)
    mongo_client.close()
    pg_engine.dispose()


if __name__ == "__main__":
    main()
