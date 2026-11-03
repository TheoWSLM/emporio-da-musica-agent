"""Test doubles shared by the test suites (deterministic embedder, frozen clock, SSE parsing)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

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


class FixedClock:
    """Fully frozen clock, for tests."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def today(self) -> date:
        return self._moment.date()


def sse_events(body: str) -> list[dict[str, Any]]:
    """Parses a Server-Sent Events body into the JSON payloads."""
    return [json.loads(line[5:].strip()) for line in body.splitlines() if line.startswith("data:")]
