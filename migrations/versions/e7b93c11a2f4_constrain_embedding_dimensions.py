"""constrain embedding dimensions

Revision ID: e7b93c11a2f4
Revises: c1b48e2d6a31
Create Date: 2026-08-19 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e7b93c11a2f4"
down_revision: Union[str, Sequence[str], None] = (
    "c1b48e2d6a31"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f(
            "ck_runbook_embeddings_"
            "embedding_dimensions_expected"
        ),
        "runbook_embeddings",
        "embedding_dimensions = 1536",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(
            "ck_runbook_embeddings_"
            "embedding_dimensions_expected"
        ),
        "runbook_embeddings",
        type_="check",
    )
