"""Ports for retrieval-augmented generation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from emporio.knowledge.domain.models import PolicyHit


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class PolicyRetriever(Protocol):
    async def search(self, query: str, k: int = 4) -> list[PolicyHit]: ...
