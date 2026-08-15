from openai import AsyncOpenAI


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
    ) -> None:
        self._client = client
        self._model = model

    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            raise ValueError(
                "At least one text is required"
            )

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            encoding_format="float",
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