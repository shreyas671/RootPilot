from math import sqrt

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


def cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    if len(left) != len(right):
        raise ValueError(
            "Embedding dimensions must match"
        )

    if not left:
        raise ValueError("Embeddings cannot be empty")

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(
            left,
            right,
            strict=True,
        )
    )

    left_norm = sqrt(
        sum(value * value for value in left)
    )
    right_norm = sqrt(
        sum(value * value for value in right)
    )

    if left_norm == 0 or right_norm == 0:
        raise ValueError(
            "Embeddings cannot be zero vectors"
        )

    return dot_product / (left_norm * right_norm)


class InMemoryRunbookRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        sections: list[RunbookSection],
        section_embeddings: list[list[float]],
    ) -> None:
        self._embedding_provider = embedding_provider
        self._sections = sections
        self._section_embeddings = section_embeddings

    @classmethod
    async def create(
        cls,
        embedding_provider: EmbeddingProvider,
        sections: list[RunbookSection],
    ) -> "InMemoryRunbookRetriever":
        if not sections:
            raise ValueError(
                "At least one runbook section is required"
            )

        section_texts = [
            build_runbook_search_text(section)
            for section in sections
        ]

        section_embeddings = (
            await embedding_provider.embed_texts(
                section_texts
            )
        )

        if len(section_embeddings) != len(sections):
            raise ValueError(
                "Embedding provider returned an unexpected "
                "number of embeddings"
            )

        return cls(
            embedding_provider=embedding_provider,
            sections=sections,
            section_embeddings=section_embeddings,
        )

    async def retrieve(
        self,
        incident: IncidentEvidence,
        limit: int = 3,
    ) -> list[RetrievedRunbookSection]:
        if limit < 1:
            raise ValueError(
                "Retrieval limit must be at least 1"
            )

        query = build_incident_query(incident)

        query_embeddings = (
            await self._embedding_provider.embed_texts(
                [query]
            )
        )

        if len(query_embeddings) != 1:
            raise ValueError(
                "Embedding provider must return one "
                "query embedding"
            )

        query_embedding = query_embeddings[0]
        results: list[RetrievedRunbookSection] = []

        for section, section_embedding in zip(
            self._sections,
            self._section_embeddings,
            strict=True,
        ):
            score = cosine_similarity(
                query_embedding,
                section_embedding,
            )

            score = max(-1.0, min(1.0, score))

            results.append(
                RetrievedRunbookSection(
                    section=section,
                    score=score,
                )
            )

        results.sort(
            key=lambda result: (
                -result.score,
                result.section.citation_id,
            )
        )

        return results[:limit]