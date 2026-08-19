from apps.metadata_service.config import Settings
from apps.metadata_service.database import get_session_factory
from apps.metadata_service.schemas.runbook import (
    RunbookSection,
)
from apps.metadata_service.services.embedding import (
    EmbeddingProvider,
)
from apps.metadata_service.services.postgres_retriever import (
    PostgresRunbookRetriever,
)
from apps.metadata_service.services.retriever import (
    InMemoryRunbookRetriever,
    RunbookRetriever,
)


async def create_runbook_retriever(
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    sections: list[RunbookSection],
) -> RunbookRetriever:
    if settings.retrieval_backend == "postgres":
        return await PostgresRunbookRetriever.create(
            embedding_provider=embedding_provider,
            session_factory=get_session_factory(),
            embedding_model=(
                settings.openai_embedding_model
            ),
            embedding_dimensions=(
                settings.embedding_dimensions
            ),
            sections=sections,
        )

    return await InMemoryRunbookRetriever.create(
        embedding_provider=embedding_provider,
        sections=sections,
    )
