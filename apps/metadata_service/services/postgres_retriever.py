from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.metadata_service.models.runbook_embedding import (
    EMBEDDING_DIMENSIONS,
    RunbookEmbedding,
)
from apps.metadata_service.schemas.incident import (
    IncidentEvidence,
)
from apps.metadata_service.schemas.retrieval import (
    RetrievedRunbookSection,
)
from apps.metadata_service.schemas.runbook import (
    RunbookSection,
)
from apps.metadata_service.services.embedding import (
    EmbeddingProvider,
)
from apps.metadata_service.services.retrieval_text import (
    build_incident_query,
    build_runbook_search_text,
)

SessionFactory = Callable[
    [],
    AbstractAsyncContextManager[AsyncSession],
]


def runbook_content_hash(
    section: RunbookSection,
) -> str:
    search_text = build_runbook_search_text(section)

    return sha256(
        search_text.encode("utf-8")
    ).hexdigest()


class PostgresRunbookRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        session_factory: SessionFactory,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        if embedding_dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                "PostgreSQL retrieval requires "
                f"{EMBEDDING_DIMENSIONS}-dimension embeddings"
            )

        self._embedding_provider = embedding_provider
        self._session_factory = session_factory
        self._embedding_model = embedding_model
        self._embedding_dimensions = (
            embedding_dimensions
        )

    @classmethod
    async def create(
        cls,
        embedding_provider: EmbeddingProvider,
        session_factory: SessionFactory,
        embedding_model: str,
        sections: list[RunbookSection],
        embedding_dimensions: int = (
            EMBEDDING_DIMENSIONS
        ),
    ) -> "PostgresRunbookRetriever":
        retriever = cls(
            embedding_provider=embedding_provider,
            session_factory=session_factory,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )
        await retriever.index_sections(sections)

        return retriever

    async def index_sections(
        self,
        sections: list[RunbookSection],
    ) -> int:
        if not sections:
            raise ValueError(
                "At least one runbook section is required"
            )

        section_hashes = {
            section.citation_id: runbook_content_hash(
                section
            )
            for section in sections
        }

        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    RunbookEmbedding.citation_id,
                    RunbookEmbedding.content_hash,
                    RunbookEmbedding.embedding_model,
                )
            )
            existing = {
                row.citation_id: (
                    row.content_hash,
                    row.embedding_model,
                )
                for row in result
            }

        changed_sections = [
            section
            for section in sections
            if existing.get(section.citation_id)
            != (
                section_hashes[section.citation_id],
                self._embedding_model,
            )
        ]

        if changed_sections:
            embeddings = (
                await self._embedding_provider.embed_texts(
                    [
                        build_runbook_search_text(section)
                        for section in changed_sections
                    ]
                )
            )

            if len(embeddings) != len(changed_sections):
                raise ValueError(
                    "Embedding provider returned an "
                    "unexpected number of embeddings"
                )

            for embedding in embeddings:
                if len(embedding) != (
                    self._embedding_dimensions
                ):
                    raise ValueError(
                        "Embedding provider returned an "
                        "unexpected vector dimension"
                    )

            values = [
                {
                    "citation_id": section.citation_id,
                    "runbook_id": section.runbook_id,
                    "runbook_title": (
                        section.runbook_title
                    ),
                    "section_title": section.section_title,
                    "content": section.content,
                    "source_file": section.source_file,
                    "content_hash": section_hashes[
                        section.citation_id
                    ],
                    "embedding_model": (
                        self._embedding_model
                    ),
                    "embedding_dimensions": (
                        self._embedding_dimensions
                    ),
                    "embedding": embedding,
                }
                for section, embedding in zip(
                    changed_sections,
                    embeddings,
                    strict=True,
                )
            ]
            statement = insert(RunbookEmbedding).values(
                values
            )
            update_values = {
                column: getattr(statement.excluded, column)
                for column in (
                    "runbook_id",
                    "runbook_title",
                    "section_title",
                    "content",
                    "source_file",
                    "content_hash",
                    "embedding_model",
                    "embedding_dimensions",
                    "embedding",
                )
            }

            statement = statement.on_conflict_do_update(
                index_elements=[
                    RunbookEmbedding.citation_id
                ],
                set_=update_values,
            )

            async with self._session_factory() as session:
                await session.execute(statement)
                await session.commit()

        current_citation_ids = list(section_hashes)

        async with self._session_factory() as session:
            await session.execute(
                delete(RunbookEmbedding).where(
                    RunbookEmbedding.citation_id.not_in(
                        current_citation_ids
                    )
                )
            )
            await session.commit()

        return len(changed_sections)

    async def retrieve(
        self,
        incident: IncidentEvidence,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        if limit < 1:
            raise ValueError(
                "Retrieval limit must be at least 1"
            )

        query_embeddings = (
            await self._embedding_provider.embed_texts(
                [build_incident_query(incident)]
            )
        )

        if len(query_embeddings) != 1:
            raise ValueError(
                "Embedding provider must return one "
                "query embedding"
            )

        query_embedding = query_embeddings[0]

        if len(query_embedding) != self._embedding_dimensions:
            raise ValueError(
                "Query embedding has an unexpected dimension"
            )

        distance = (
            RunbookEmbedding.embedding.cosine_distance(
                query_embedding
            ).label("distance")
        )
        statement = (
            select(RunbookEmbedding, distance)
            .where(
                RunbookEmbedding.embedding_model
                == self._embedding_model
            )
            .order_by(
                distance,
                RunbookEmbedding.citation_id,
            )
            .limit(limit)
        )

        async with self._session_factory() as session:
            rows = (
                await session.execute(statement)
            ).all()

        results = []

        for record, raw_distance in rows:
            score = 1.0 - float(raw_distance)
            score = max(-1.0, min(1.0, score))
            results.append(
                RetrievedRunbookSection(
                    section=RunbookSection(
                        runbook_id=record.runbook_id,
                        runbook_title=(
                            record.runbook_title
                        ),
                        section_title=(
                            record.section_title
                        ),
                        citation_id=record.citation_id,
                        content=record.content,
                        source_file=record.source_file,
                    ),
                    score=score,
                )
            )

        return results
