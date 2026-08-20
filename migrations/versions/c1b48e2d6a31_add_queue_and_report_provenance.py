"""add queue and report provenance

Revision ID: c1b48e2d6a31
Revises: 9f82c4a17d90
Create Date: 2026-08-19 17:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1b48e2d6a31"
down_revision: str | Sequence[str] | None = (
    "9f82c4a17d90"
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "incident_id",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "claimed_by",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_jobs_attempt_count_nonnegative"),
        "jobs",
        "attempt_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_jobs_max_attempts_positive"),
        "jobs",
        "max_attempts >= 1",
    )
    op.create_check_constraint(
        op.f("ck_jobs_attempt_count_within_limit"),
        "jobs",
        "attempt_count <= max_attempts",
    )
    op.create_index(
        op.f("ix_jobs_incident_id"),
        "jobs",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_jobs_scheduled_at"),
        "jobs",
        ["scheduled_at"],
        unique=False,
    )

    op.add_column(
        "investigation_reports",
        sa.Column(
            "embedding_model",
            sa.String(length=255),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "analysis_model",
            sa.String(length=255),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "prompt_version",
            sa.String(length=128),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "retrieval_backend",
            sa.String(length=32),
            server_default="memory",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "retrieval_limit",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "minimum_relevance_score",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "retrieved_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f(
            "ck_investigation_reports_"
            "minimum_relevance_score_range"
        ),
        "investigation_reports",
        "minimum_relevance_score >= -1.0 AND "
        "minimum_relevance_score <= 1.0",
    )
    op.create_check_constraint(
        op.f(
            "ck_investigation_reports_"
            "retrieval_limit_positive"
        ),
        "investigation_reports",
        "retrieval_limit >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(
            "ck_investigation_reports_"
            "retrieval_limit_positive"
        ),
        "investigation_reports",
        type_="check",
    )
    op.drop_constraint(
        op.f(
            "ck_investigation_reports_"
            "minimum_relevance_score_range"
        ),
        "investigation_reports",
        type_="check",
    )
    for column in (
        "retrieved_sections",
        "minimum_relevance_score",
        "retrieval_limit",
        "retrieval_backend",
        "prompt_version",
        "analysis_model",
        "embedding_model",
    ):
        op.drop_column("investigation_reports", column)

    op.drop_index(
        op.f("ix_jobs_scheduled_at"),
        table_name="jobs",
    )
    op.drop_index(
        op.f("ix_jobs_incident_id"),
        table_name="jobs",
    )
    op.drop_constraint(
        op.f("ck_jobs_attempt_count_within_limit"),
        "jobs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_jobs_max_attempts_positive"),
        "jobs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_jobs_attempt_count_nonnegative"),
        "jobs",
        type_="check",
    )
    for column in (
        "scheduled_at",
        "lease_expires_at",
        "claimed_by",
        "max_attempts",
        "attempt_count",
        "incident_id",
    ):
        op.drop_column("jobs", column)
