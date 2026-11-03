"""Embedding adapters."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
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


_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Deterministic bag-of-words embedder (feature hashing). Used in tests and as an offline fallback;
    it captures lexical overlap only."""

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        vector = [0.0] * self._dimensions
        for word in _WORD.findall(normalized):
            if len(word) < 3:
                continue
            bucket = int.from_bytes(
                hashlib.blake2b(word[:6].encode(), digest_size=4).digest(), "big"
            )
            vector[bucket % self._dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]
