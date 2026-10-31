"""add react investigation provenance

Revision ID: f2a84c7d3e10
Revises: e7b93c11a2f4
Create Date: 2026-10-30 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a84c7d3e10"
down_revision: str | Sequence[str] | None = (
    "e7b93c11a2f4"
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "investigation_reports",
        sa.Column(
            "investigation_mode",
            sa.String(length=32),
            server_default="single_pass",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "react_termination_reason",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "react_iterations",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "react_tool_calls",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "investigation_reports",
        sa.Column(
            "react_trajectory",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_investigation_reports_react_iterations_nonnegative"),
        "investigation_reports",
        "react_iterations >= 0",
    )
    op.create_check_constraint(
        op.f("ck_investigation_reports_react_tool_calls_nonnegative"),
        "investigation_reports",
        "react_tool_calls >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_investigation_reports_react_tool_calls_nonnegative"),
        "investigation_reports",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_reports_react_iterations_nonnegative"),
        "investigation_reports",
        type_="check",
    )
    op.drop_column(
        "investigation_reports",
        "react_trajectory",
    )
    op.drop_column(
        "investigation_reports",
        "react_tool_calls",
    )
    op.drop_column(
        "investigation_reports",
        "react_iterations",
    )
    op.drop_column(
        "investigation_reports",
        "react_termination_reason",
    )
    op.drop_column(
        "investigation_reports",
        "investigation_mode",
    )
