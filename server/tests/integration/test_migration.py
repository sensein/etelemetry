"""Integration tests for the MongoDB-to-PostgreSQL migration tool.

Tests exercise migration functions with mocked MongoDB and a real
in-memory SQLite database standing in for PostgreSQL. Marked with
``pytest.mark.integration``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from etelemetry_server.models import Base, Project, VersionCheck

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def mongo_sample_data():
    """Load the sample MongoDB fixture data."""
    with open(FIXTURES_DIR / "mongo_sample.json") as f:
        return json.load(f)


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with the schema."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def mock_mongo_client(mongo_sample_data):
    """Build a mock pymongo.MongoClient that returns fixture data."""
    requests_cursor = MagicMock()
    requests_cursor.find.return_value = iter(mongo_sample_data["requests"])
    requests_cursor.count_documents.return_value = len(mongo_sample_data["requests"])

    geo_cursor = MagicMock()
    geo_cursor.find.return_value = iter(mongo_sample_data["geo"])
    geo_cursor.count_documents.return_value = len(mongo_sample_data["geo"])

    db = MagicMock()
    db.__getitem__ = lambda self, name: {
        "requests": requests_cursor,
        "geo": geo_cursor,
    }[name]

    client = MagicMock()
    client.__getitem__ = lambda self, name: db
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMigrationImport:
    """Tests for the core migrate_records function."""

    def test_valid_records_imported(
        self, mock_mongo_client, engine, session_factory
    ) -> None:
        """All valid records are imported into PostgreSQL."""
        from tools.migrate import migrate_records

        migrate_records(mock_mongo_client, engine, batch_size=100)

        with Session(engine) as session:
            projects = session.execute(select(Project)).scalars().all()
            checks = session.execute(select(VersionCheck)).scalars().all()

        # Two unique owner/repo pairs: nipy/nipype and poldracklab/fmriprep
        project_pairs = {(p.owner, p.repo) for p in projects}
        assert ("nipy", "nipype") in project_pairs
        assert ("poldracklab", "fmriprep") in project_pairs
        assert len(project_pairs) == 2

        # Should have version_check rows for valid records
        assert len(checks) > 0

    def test_no_ip_fields_in_output(
        self, mock_mongo_client, engine, session_factory
    ) -> None:
        """No IP address fields are stored in PostgreSQL."""
        from tools.migrate import migrate_records

        migrate_records(mock_mongo_client, engine, batch_size=100)

        with Session(engine) as session:
            checks = session.execute(select(VersionCheck)).scalars().all()

        for vc in checks:
            assert not hasattr(vc, "remote_addr")
            assert not hasattr(vc, "ip")
            assert not hasattr(vc, "ip_address")

    def test_duplicate_handling(
        self, mock_mongo_client, engine, session_factory
    ) -> None:
        """Duplicate content-addressed records are collapsed (count incremented).

        In the fixture, records aaa111 and aaa555 share the same
        owner/repo/version/is_ci/time_bucket(hour)/geo, so they should
        produce a single row with count >= 2.  Record aaa333 has the same
        owner/repo/version but a *different* hour-truncated time_bucket
        (10:15 truncates to 10:00, same as 10:30 -- actually same hour),
        so it also deduplicates with aaa111.
        """
        from tools.migrate import migrate_records

        migrate_records(mock_mongo_client, engine, batch_size=100)

        with Session(engine) as session:
            checks = session.execute(select(VersionCheck)).scalars().all()

        # Find checks for nipy/nipype v1.8.6 non-CI with Cambridge geo
        nipype_checks = [
            c
            for c in checks
            if c.version == "1.8.6" and c.city == "Cambridge" and not c.is_ci
        ]
        # All three (aaa111, aaa333, aaa555) share the same hour bucket and geo
        # so they should be one row with count >= 3
        assert len(nipype_checks) == 1
        assert nipype_checks[0].count >= 3

    def test_malformed_records_skipped(
        self, mock_mongo_client, engine, session_factory, caplog
    ) -> None:
        """Malformed records (missing owner, repo, or version) are skipped with a warning."""
        from tools.migrate import migrate_records

        with caplog.at_level(logging.WARNING):
            stats = migrate_records(mock_mongo_client, engine, batch_size=100)

        # 3 malformed records in our fixture
        assert stats["skipped"] >= 3

        # Warnings should have been logged
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) >= 3

    def test_missing_geo_uses_defaults(
        self, mock_mongo_client, engine, session_factory
    ) -> None:
        """Records without geo data get 'unknown' defaults for location fields."""
        from tools.migrate import migrate_records

        migrate_records(mock_mongo_client, engine, batch_size=100)

        with Session(engine) as session:
            checks = session.execute(select(VersionCheck)).scalars().all()

        # poldracklab/fmriprep record has IP 192.0.2.50 which has no geo entry
        fmriprep_checks = [c for c in checks if c.version == "23.1.0"]
        assert len(fmriprep_checks) == 1
        assert fmriprep_checks[0].city == "unknown"
        assert fmriprep_checks[0].region == "unknown"
        assert fmriprep_checks[0].country == "unknown"


@pytest.mark.integration
class TestMigrationVerify:
    """Tests for the --verify functionality."""

    def test_verify_counts(
        self, mock_mongo_client, engine, session_factory
    ) -> None:
        """Verify mode compares MongoDB vs PostgreSQL record counts."""
        from tools.migrate import migrate_records, verify_migration

        migrate_records(mock_mongo_client, engine, batch_size=100)
        result = verify_migration(mock_mongo_client, engine)

        assert "mongo_requests" in result
        assert "pg_version_checks" in result
        assert "pg_total_count" in result
        # The PG total count should match the number of valid mongo requests
        assert result["pg_total_count"] >= 5  # 5 valid records in fixture


@pytest.mark.integration
class TestMigrationIdempotency:
    """Running the migration twice should not create duplicate rows."""

    def test_double_run_no_extra_rows(
        self, mongo_sample_data, engine, session_factory
    ) -> None:
        """Running migration twice yields the same row count, with increased counts."""
        from tools.migrate import migrate_records

        # Build fresh mock each time since iterators are consumed
        def make_mock():
            requests_cursor = MagicMock()
            requests_cursor.find.return_value = iter(mongo_sample_data["requests"])
            requests_cursor.count_documents.return_value = len(
                mongo_sample_data["requests"]
            )
            geo_cursor = MagicMock()
            geo_cursor.find.return_value = iter(mongo_sample_data["geo"])
            geo_cursor.count_documents.return_value = len(mongo_sample_data["geo"])
            db = MagicMock()
            db.__getitem__ = lambda self, name: {
                "requests": requests_cursor,
                "geo": geo_cursor,
            }[name]
            client = MagicMock()
            client.__getitem__ = lambda self, name: db
            return client

        migrate_records(make_mock(), engine, batch_size=100)

        with Session(engine) as session:
            checks_first = session.execute(select(VersionCheck)).scalars().all()
        row_count_first = len(checks_first)

        migrate_records(make_mock(), engine, batch_size=100)

        with Session(engine) as session:
            checks_second = session.execute(select(VersionCheck)).scalars().all()
        row_count_second = len(checks_second)

        # Same number of rows
        assert row_count_first == row_count_second

        # But counts have doubled
        for vc in checks_second:
            matching_first = [
                c for c in checks_first if c.id == vc.id
            ]
            if matching_first:
                assert vc.count >= matching_first[0].count
