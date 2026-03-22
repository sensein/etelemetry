"""Initial schema — projects, version_checks, usage_aggregates.

Revision ID: 001
Revises: None
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("latest_version", sa.String(100), nullable=True),
        sa.Column("bad_versions", sa.JSON, server_default="[]"),
        sa.Column(
            "cache_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("active", sa.Boolean, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("owner", "repo", name="uq_project_owner_repo"),
    )
    op.create_index(
        "ix_project_owner_repo", "projects", ["owner", "repo"]
    )

    # --- version_checks ---
    op.create_table(
        "version_checks",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("is_ci", sa.Boolean, server_default=sa.text("false")),
        sa.Column("time_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_id",
            "version",
            "city",
            "region",
            "country_code",
            "is_ci",
            "time_bucket",
            name="uq_version_check_content_address",
        ),
    )
    op.create_index(
        "ix_version_check_project_bucket",
        "version_checks",
        ["project_id", "time_bucket"],
    )
    op.create_index(
        "ix_version_check_bucket", "version_checks", ["time_bucket"]
    )

    # --- usage_aggregates ---
    op.create_table(
        "usage_aggregates",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("version", sa.String(100), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("granularity", sa.String(10), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("total_count", sa.BigInteger, server_default=sa.text("0")),
        sa.Column(
            "unique_locations", sa.Integer, server_default=sa.text("0")
        ),
        sa.Column("ci_count", sa.BigInteger, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_id",
            "version",
            "country_code",
            "region",
            "granularity",
            "period_start",
            name="uq_usage_aggregate_key",
        ),
    )
    op.create_index(
        "ix_usage_aggregate_project_granularity",
        "usage_aggregates",
        ["project_id", "granularity", "period_start"],
    )


def downgrade() -> None:
    op.drop_table("usage_aggregates")
    op.drop_table("version_checks")
    op.drop_table("projects")
