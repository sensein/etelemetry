"""SQLAlchemy 2.0 ORM models."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all models."""

    pass


class Project(Base):
    """Tracks registered projects (owner/repo pairs)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_version: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    bad_versions: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    cache_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    version_checks: Mapped[list["VersionCheck"]] = relationship(
        back_populates="project"
    )
    usage_aggregates: Mapped[list["UsageAggregate"]] = relationship(
        back_populates="project"
    )

    __table_args__ = (
        UniqueConstraint("owner", "repo", name="uq_project_owner_repo"),
        Index("ix_project_owner_repo", "owner", "repo"),
    )


class VersionCheck(Base):
    """Content-addressable version-check records, bucketed by time."""

    __tablename__ = "version_checks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_ci: Mapped[bool] = mapped_column(Boolean, default=False)
    time_bucket: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="version_checks")

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "version",
            "city",
            "region",
            "country_code",
            "is_ci",
            "time_bucket",
            name="uq_version_check_content_address",
        ),
        Index("ix_version_check_project_bucket", "project_id", "time_bucket"),
        Index("ix_version_check_bucket", "time_bucket"),
    )


class UsageAggregate(Base):
    """Pre-aggregated usage statistics per period."""

    __tablename__ = "usage_aggregates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True
    )
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    granularity: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    total_count: Mapped[int] = mapped_column(BigInteger, default=0)
    unique_locations: Mapped[int] = mapped_column(Integer, default=0)
    ci_count: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="usage_aggregates")

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "version",
            "country_code",
            "region",
            "granularity",
            "period_start",
            name="uq_usage_aggregate_key",
        ),
        Index(
            "ix_usage_aggregate_project_granularity",
            "project_id",
            "granularity",
            "period_start",
        ),
    )
