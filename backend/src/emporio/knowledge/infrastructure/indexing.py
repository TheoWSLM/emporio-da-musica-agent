"""Builds the policy chunks from the manual (structural chunking + semantic fallback)."""

from __future__ import annotations

from pathlib import Path

from emporio.knowledge.application.ports import Embedder
from emporio.knowledge.domain.models import PolicyChunk
from emporio.knowledge.infrastructure.chunking import (
    MAX_TOKENS,
    oversized_sections,
    paragraphs_of,
    semantic_split,
    structural_chunks,
    to_chunks,
)
from emporio.knowledge.infrastructure.pdf_parser import parse_pdf


async def build_policy_chunks(
    pdf_path: Path, embedder: Embedder, max_tokens: int = MAX_TOKENS
) -> list[PolicyChunk]:
    sections = structural_chunks(parse_pdf(pdf_path))
    oversized: dict[str, list[str]] = {}
    for section in oversized_sections(sections, max_tokens):
        paragraphs = paragraphs_of(section)
        oversized[section.path] = semantic_split(
            paragraphs, await embedder.embed(paragraphs), max_tokens
        )
    return to_chunks(sections, oversized)
