from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.metadata_service.services.openai_embedding import (
    OpenAIEmbeddingProvider,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_embed_texts_returns_ordered_vectors() -> None:
    create_embedding = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=1,
                    embedding=[0.0, 1.0],
                ),
                SimpleNamespace(
                    index=0,
                    embedding=[1.0, 0.0],
                ),
            ]
        )
    )

    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=create_embedding,
        )
    )

    provider = OpenAIEmbeddingProvider(
        client=client,
        model="text-embedding-test",
    )

    embeddings = await provider.embed_texts(
        [
            "database incident",
            "kafka incident",
        ]
    )

    assert embeddings == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]

    create_embedding.assert_awaited_once_with(
        model="text-embedding-test",
        input=[
            "database incident",
            "kafka incident",
        ],
        encoding_format="float",
    )


@pytest.mark.anyio
async def test_embed_texts_rejects_empty_input() -> None:
    create_embedding = AsyncMock()

    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=create_embedding,
        )
    )

    provider = OpenAIEmbeddingProvider(
        client=client,
        model="text-embedding-test",
    )

    with pytest.raises(
        ValueError,
        match="At least one text is required",
    ):
        await provider.embed_texts([])

    create_embedding.assert_not_awaited()