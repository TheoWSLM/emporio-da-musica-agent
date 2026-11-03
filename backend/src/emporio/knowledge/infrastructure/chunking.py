"""Chunking strategies.

Structural chunking (primary): one chunk per subsection of the manual (or per section when it has no
subsections), carrying its heading path. Each subsection is one complete rule, so cutting by a fixed
size would separate a rule from its exception.

Semantic fallback: a section longer than `max_tokens` is split between paragraphs where the
similarity of consecutive paragraph embeddings drops the most. The current manual never triggers it,
but the strategy keeps chunks bounded if the manual grows.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from emporio.knowledge.domain.models import PolicyChunk
from emporio.knowledge.infrastructure.pdf_parser import Element, Kind

MAX_TOKENS = 500
_SENTENCE_END = re.compile(r"[.:;!?)]$")


@dataclass
class _Section:
    path: str
    heading: str
    parts: list[str] = field(default_factory=list)


def _join_lines(lines: Sequence[str]) -> str:
    """Re-flows PDF lines into paragraphs: a line continues the previous one unless the previous one
    ended a sentence or the new one starts a list item."""
    paragraphs: list[str] = []
    for line in lines:
        starts_item = line.startswith("- ") or bool(re.match(r"^\d+\. ", line))
        if paragraphs and not starts_item and not _SENTENCE_END.search(paragraphs[-1]):
            paragraphs[-1] = f"{paragraphs[-1]} {line}"
        else:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def structural_chunks(elements: Sequence[Element]) -> list[_Section]:
    sections: list[_Section] = []
    section_title = ""
    current: _Section | None = None
    lines: list[str] = []

    def flush() -> None:
        if current is not None and lines:
            current.parts.append(_join_lines(lines))
        lines.clear()

    for element in elements:
        if element.kind is Kind.SECTION:
            flush()
            section_title = element.text
            current = _Section(section_title, section_title)
            sections.append(current)
        elif element.kind is Kind.SUBSECTION:
            flush()
            current = _Section(f"{section_title} > {element.text}", element.text)
            sections.append(current)
        elif current is not None:
            if element.kind is Kind.TABLE:
                flush()
                current.parts.append(element.text)
            else:
                lines.append(element.text)
    flush()
    return [s for s in sections if s.parts]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def semantic_split(
    paragraphs: Sequence[str], embeddings: Sequence[Sequence[float]], max_tokens: int
) -> list[str]:
    """Recursively cuts at the weakest link between consecutive paragraphs until every piece fits."""
    text = "\n".join(paragraphs)
    if len(paragraphs) < 2 or len(text) // 4 <= max_tokens:
        return [text]
    similarities = [_cosine(embeddings[i], embeddings[i + 1]) for i in range(len(paragraphs) - 1)]
    cut = similarities.index(min(similarities)) + 1
    return semantic_split(paragraphs[:cut], embeddings[:cut], max_tokens) + semantic_split(
        paragraphs[cut:], embeddings[cut:], max_tokens
    )


def to_chunks(
    sections: Sequence[_Section], oversized: dict[str, list[str]] | None = None
) -> list[PolicyChunk]:
    """`oversized` maps a section path to its semantic pieces (computed by the caller, which owns
    the embedder)."""
    chunks: list[PolicyChunk] = []
    for section in sections:
        pieces = (oversized or {}).get(section.path) or ["\n".join(section.parts)]
        for index, piece in enumerate(pieces, start=1):
            suffix = f" (parte {index})" if len(pieces) > 1 else ""
            chunks.append(PolicyChunk(len(chunks), section.path + suffix, section.heading, piece))
    return chunks


def oversized_sections(
    sections: Sequence[_Section], max_tokens: int = MAX_TOKENS
) -> list[_Section]:
    return [s for s in sections if len("\n".join(s.parts)) // 4 > max_tokens]


def paragraphs_of(section: _Section) -> list[str]:
    return [p for part in section.parts for p in part.split("\n") if p.strip()]
