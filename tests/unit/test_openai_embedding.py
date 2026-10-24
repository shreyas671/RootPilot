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


@pytest.mark.anyio
async def test_embed_texts_accepts_exact_storage_dimensions() -> None:
    create_embedding = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=0,
                    embedding=[0.25, 0.75, 0.5, 0.1],
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
        model="embedding-model-test",
        dimensions=4,
    )

    embeddings = await provider.embed_texts(["incident"])

    assert embeddings == [[0.25, 0.75, 0.5, 0.1]]
    create_embedding.assert_awaited_once_with(
        model="embedding-model-test",
        input=["incident"],
        encoding_format="float",
    )


@pytest.mark.anyio
async def test_embed_texts_pads_shorter_gateway_vectors() -> None:
    create_embedding = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=0,
                    embedding=[0.25, 0.75],
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
        model="embedding-model-test",
        dimensions=4,
    )

    embeddings = await provider.embed_texts(["incident"])

    assert embeddings == [[0.25, 0.75, 0.0, 0.0]]


@pytest.mark.anyio
async def test_embed_texts_rejects_oversized_vectors() -> None:
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[
                        SimpleNamespace(
                            index=0,
                            embedding=[0.1, 0.2, 0.3],
                        ),
                    ]
                )
            ),
        )
    )
    provider = OpenAIEmbeddingProvider(
        client=client,
        model="embedding-test",
        dimensions=2,
    )

    with pytest.raises(
        ValueError,
        match="more dimensions",
    ):
        await provider.embed_texts(["incident"])
