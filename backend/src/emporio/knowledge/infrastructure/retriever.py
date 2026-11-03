"""Hybrid policy retrieval: pgvector cosine + Portuguese full-text, fused with Reciprocal Rank Fusion."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.infrastructure.orm import PolicyChunkRow
from emporio.knowledge.application.ports import Embedder
from emporio.knowledge.domain.models import PolicyHit

RRF_K = 60
CANDIDATES = 8


class SqlPolicyRetriever:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder) -> None:
        self._sessions = sessions
        self._embedder = embedder

    async def search(
        self, query: str, k: int = 4, embedding: Sequence[float] | None = None
    ) -> list[PolicyHit]:
        if embedding is None:
            embedding = (await self._embedder.embed([query]))[0]
        distance = PolicyChunkRow.embedding.cosine_distance(list(embedding))
        tsquery = func.websearch_to_tsquery("portuguese", query)
        rank = func.ts_rank_cd(PolicyChunkRow.content_tsv, tsquery)
        async with self._sessions() as session:
            vector_rows = (
                await session.execute(
                    select(PolicyChunkRow, (1 - distance).label("similarity"))
                    .where(PolicyChunkRow.embedding.is_not(None))
                    .order_by(distance)
                    .limit(CANDIDATES)
                )
            ).all()
            text_rows = (
                await session.scalars(
                    select(PolicyChunkRow)
                    .where(PolicyChunkRow.content_tsv.op("@@")(tsquery))
                    .order_by(rank.desc())
                    .limit(CANDIDATES)
                )
            ).all()

        chunks: dict[int, PolicyChunkRow] = {}
        fused: dict[int, float] = {}
        similarity: dict[int, float] = {}
        for position, (row, sim) in enumerate(vector_rows):
            chunks[row.id] = row
            similarity[row.id] = float(sim)
            fused[row.id] = fused.get(row.id, 0.0) + 1.0 / (RRF_K + position + 1)
        for position, row in enumerate(text_rows):
            chunks[row.id] = row
            fused[row.id] = fused.get(row.id, 0.0) + 1.0 / (RRF_K + position + 1)

        ranked = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)[:k]
        return [
            PolicyHit(
                section_path=chunks[i].section_path,
                heading=chunks[i].heading,
                content=chunks[i].content,
                score=round(fused[i], 5),
                similarity=round(similarity.get(i, 0.0), 4),
            )
            for i in ranked
        ]
