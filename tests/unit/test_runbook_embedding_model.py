from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint

from apps.metadata_service.models import (
    Base,
    RunbookEmbedding,
)


def test_runbook_embedding_table_metadata() -> None:
    table = RunbookEmbedding.__table__

    assert table.name == "runbook_embeddings"
    assert Base.metadata.tables[table.name] is table
    assert table.c.citation_id.primary_key
    assert isinstance(table.c.embedding.type, Vector)
    assert table.c.embedding.type.dim == 1536

    constraints = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints == {
        "ck_runbook_embeddings_embedding_dimensions_expected"
    }
