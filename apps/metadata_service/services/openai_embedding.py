from openai import AsyncOpenAI


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

        if self._dimensions is not None:
            request["dimensions"] = self._dimensions

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
            item.embedding
            for item in response_data
        ]
