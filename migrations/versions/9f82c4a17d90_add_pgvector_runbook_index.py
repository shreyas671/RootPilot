"""add pgvector runbook index

Revision ID: 9f82c4a17d90
Revises: 5d6d6a46d37e
Create Date: 2026-08-19 17:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "9f82c4a17d90"
down_revision: str | Sequence[str] | None = (
    "5d6d6a46d37e"
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "runbook_embeddings",
        sa.Column(
            "citation_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "runbook_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "runbook_title",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "section_title",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "source_file",
            sa.String(length=1024),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            Vector(1536),
            nullable=False,
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "citation_id",
            name=op.f("pk_runbook_embeddings"),
        ),
    )
    op.create_index(
        op.f("ix_runbook_embeddings_embedding_model"),
        "runbook_embeddings",
        ["embedding_model"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runbook_embeddings_runbook_id"),
        "runbook_embeddings",
        ["runbook_id"],
        unique=False,
    )
    op.create_index(
        "ix_runbook_embeddings_embedding_hnsw",
        "runbook_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={
            "embedding": "vector_cosine_ops",
        },
        postgresql_with={
            "m": 16,
            "ef_construction": 64,
        },
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runbook_embeddings_embedding_hnsw",
        table_name="runbook_embeddings",
        postgresql_using="hnsw",
    )
    op.drop_index(
        op.f("ix_runbook_embeddings_runbook_id"),
        table_name="runbook_embeddings",
    )
    op.drop_index(
        op.f("ix_runbook_embeddings_embedding_model"),
        table_name="runbook_embeddings",
    )
    op.drop_table("runbook_embeddings")
