"""Tests for etelemetry_server.models."""

import datetime

from sqlalchemy import inspect

from etelemetry_server.models import Base, Project, UsageAggregate, VersionCheck


class TestProjectModel:
    def test_tablename(self) -> None:
        assert Project.__tablename__ == "projects"

    def test_columns_exist(self) -> None:
        cols = {c.name for c in inspect(Project).columns}
        expected = {
            "id",
            "owner",
            "repo",
            "latest_version",
            "bad_versions",
            "cache_expires_at",
            "active",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_unique_constraint_on_owner_repo(self) -> None:
        table = Project.__table__
        uq_names = [
            c.name
            for c in table.constraints
            if hasattr(c, "columns")
            and {col.name for col in c.columns} == {"owner", "repo"}
        ]
        assert len(uq_names) >= 1

    def test_instantiation(self) -> None:
        p = Project(owner="nipy", repo="nipype")
        assert p.owner == "nipy"
        assert p.repo == "nipype"


class TestVersionCheckModel:
    def test_tablename(self) -> None:
        assert VersionCheck.__tablename__ == "version_checks"

    def test_columns_exist(self) -> None:
        cols = {c.name for c in inspect(VersionCheck).columns}
        expected = {
            "id",
            "project_id",
            "version",
            "city",
            "region",
            "country",
            "country_code",
            "latitude",
            "longitude",
            "is_ci",
            "time_bucket",
            "count",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_content_address_unique_constraint(self) -> None:
        table = VersionCheck.__table__
        uq = [
            c
            for c in table.constraints
            if hasattr(c, "name")
            and getattr(c, "name", None) == "uq_version_check_content_address"
        ]
        assert len(uq) == 1

    def test_instantiation(self) -> None:
        vc = VersionCheck(
            project_id=1,
            version="1.0.0",
            time_bucket=datetime.datetime.now(tz=datetime.timezone.utc),
        )
        assert vc.version == "1.0.0"


class TestUsageAggregateModel:
    def test_tablename(self) -> None:
        assert UsageAggregate.__tablename__ == "usage_aggregates"

    def test_columns_exist(self) -> None:
        cols = {c.name for c in inspect(UsageAggregate).columns}
        expected = {
            "id",
            "project_id",
            "version",
            "country_code",
            "region",
            "granularity",
            "period_start",
            "total_count",
            "unique_locations",
            "ci_count",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_instantiation(self) -> None:
        ua = UsageAggregate(
            project_id=1,
            granularity="daily",
            period_start=datetime.date(2026, 1, 1),
        )
        assert ua.granularity == "daily"


class TestBaseMetadata:
    def test_all_tables_registered(self) -> None:
        table_names = set(Base.metadata.tables.keys())
        assert "projects" in table_names
        assert "version_checks" in table_names
        assert "usage_aggregates" in table_names
