"""Policy knowledge: chunks of the store manual and retrieval hits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyChunk:
    position: int
    section_path: str
    """e.g. '4. Política de Trocas e Devoluções > 4.1 Direito de Arrependimento (Compras Online)'"""
    heading: str
    content: str

    @property
    def token_count(self) -> int:
        """Rough estimate (~4 characters per token for Portuguese) — good enough for chunk sizing."""
        return max(1, len(self.content) // 4)

    @property
    def embedding_text(self) -> str:
        """The heading path travels with the text so that short chunks keep their context."""
        return f"{self.section_path}\n{self.content}"


@dataclass(frozen=True)
class PolicyHit:
    section_path: str
    heading: str
    content: str
    score: float
    """Fused (RRF) rank score."""
    similarity: float
    """Cosine similarity of the vector match (0 when the hit came only from full-text search)."""
