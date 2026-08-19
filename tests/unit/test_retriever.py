import pytest

from apps.metadata_service.services.incident_loader import (
    load_incidents,
)
from apps.metadata_service.services.retriever import (
    InMemoryRunbookRetriever,
    cosine_similarity,
)
from apps.metadata_service.services.runbook_loader import (
    load_runbooks,
)


class KeywordEmbeddingProvider:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.batch_sizes.append(len(texts))

        return [
            self._embed_text(text)
            for text in texts
        ]

    @staticmethod
    def _embed_text(text: str) -> list[float]:
        normalized_text = text.lower()

        database_score = sum(
            normalized_text.count(keyword)
            for keyword in (
                "database",
                "postgres",
                "connection",
                "pool",
            )
        )

        kafka_score = sum(
            normalized_text.count(keyword)
            for keyword in (
                "kafka",
                "consumer",
                "partition",
                "event",
                "schema",
            )
        )

        return [
            float(database_score),
            float(kafka_score),
            1.0,
        ]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_cosine_similarity() -> None:
    assert cosine_similarity(
        [1.0, 0.0],
        [1.0, 0.0],
    ) == pytest.approx(1.0)

    assert cosine_similarity(
        [1.0, 0.0],
        [0.0, 1.0],
    ) == pytest.approx(0.0)


@pytest.mark.anyio
async def test_retriever_returns_database_sections() -> None:
    embedding_provider = KeywordEmbeddingProvider()

    retriever = await InMemoryRunbookRetriever.create(
        embedding_provider=embedding_provider,
        sections=load_runbooks(),
    )

    incident = load_incidents()["INC-DB-001"]

    results = await retriever.retrieve(
        incident,
        limit=3,
    )

    assert len(results) == 3
    assert all(
        result.section.runbook_id == "RB-DB-001"
        for result in results
    )
    assert embedding_provider.batch_sizes == [25, 1]


@pytest.mark.anyio
async def test_retriever_returns_kafka_sections() -> None:
    embedding_provider = KeywordEmbeddingProvider()

    retriever = await InMemoryRunbookRetriever.create(
        embedding_provider=embedding_provider,
        sections=load_runbooks(),
    )

    incident = load_incidents()["INC-KAFKA-001"]

    results = await retriever.retrieve(
        incident,
        limit=3,
    )

    assert len(results) == 3
    assert all(
        result.section.runbook_id == "RB-KAFKA-001"
        for result in results
    )
