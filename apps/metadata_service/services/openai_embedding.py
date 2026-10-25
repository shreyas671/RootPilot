from typing import Any

from langsmith import traceable
from openai import AsyncOpenAI


def _trace_embedding_inputs(
    inputs: dict[str, Any],
) -> dict[str, object]:
    texts = inputs.get("texts", [])
    provider = inputs.get("self")

    if not isinstance(texts, list):
        texts = []

    return {
        "model": getattr(provider, "_model", "unknown"),
        "text_count": len(texts),
        "character_count": sum(
            len(text)
            for text in texts
            if isinstance(text, str)
        ),
    }


def _trace_embedding_outputs(
    outputs: object,
) -> dict[str, int]:
    if not isinstance(outputs, list):
        return {
            "vector_count": 0,
            "dimensions": 0,
        }

    first_vector = outputs[0] if outputs else []

    return {
        "vector_count": len(outputs),
        "dimensions": (
            len(first_vector)
            if isinstance(first_vector, list)
            else 0
        ),
    }


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        dimensions: int | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions

    @traceable(
        name="rootpilot_embed_texts",
        run_type="embedding",
        process_inputs=_trace_embedding_inputs,
        process_outputs=_trace_embedding_outputs,
        tags=["rootpilot", "embedding"],
    )
    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            raise ValueError(
                "At least one text is required"
            )

        request: dict[str, object] = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }

        response = await self._client.embeddings.create(
            **request,
        )

        response_data = sorted(
            response.data,
            key=lambda item: item.index,
        )

        expected_indexes = list(range(len(texts)))
        actual_indexes = [
            item.index
            for item in response_data
        ]

        if actual_indexes != expected_indexes:
            raise ValueError(
                "Embedding response indexes do not match "
                "the input texts"
            )

        return [
            self._validate_dimensions(item.embedding)
            for item in response_data
        ]

    def _validate_dimensions(
        self,
        embedding: list[float],
    ) -> list[float]:
        if self._dimensions is None:
            return embedding

        if len(embedding) > self._dimensions:
            raise ValueError(
                "Embedding response contains more dimensions "
                "than the configured storage dimension"
            )

        # Appending zeros preserves dot products, vector norms, and
        # therefore cosine similarity. This lets a gateway's shorter
        # native vectors use the fixed vector(1536) database schema.
        return embedding + [0.0] * (
            self._dimensions - len(embedding)
        )
