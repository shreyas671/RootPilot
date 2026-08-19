from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.metadata_service.models.base import Base

EMBEDDING_DIMENSIONS = 1536


class RunbookEmbedding(Base):
    __tablename__ = "runbook_embeddings"
    __table_args__ = (
        CheckConstraint(
            f"embedding_dimensions = {EMBEDDING_DIMENSIONS}",
            name="embedding_dimensions_expected",
        ),
        Index(
            "ix_runbook_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
            postgresql_with={
                "m": 16,
                "ef_construction": 64,
            },
        ),
    )

    citation_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    runbook_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    runbook_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    section_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source_file: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
