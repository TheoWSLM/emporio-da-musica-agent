"""Embedding adapters."""

from __future__ import annotations

from collections.abc import Sequence

from openai import AsyncOpenAI


class OpenAIEmbedder:
    def __init__(
        self, client: AsyncOpenAI, model: str, dimensions: int, batch_size: int = 96
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            response = await self._client.embeddings.create(
                model=self._model, input=batch, dimensions=self._dimensions
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors
