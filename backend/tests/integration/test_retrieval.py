from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.catalog.application.ports import ProductFilter
from emporio.catalog.infrastructure.repositories import SqlProductReader
from emporio.ingestion.pipeline import ingest_embeddings
from emporio.knowledge.infrastructure.embedders import HashingEmbedder
from emporio.knowledge.infrastructure.retriever import SqlPolicyRetriever

from .conftest import DATA_DIR

EMBEDDER = HashingEmbedder()


@pytest.fixture(scope="module")
async def indexed(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    await ingest_embeddings(sessions, DATA_DIR, EMBEDDER, "hashing-test", force=True)
    yield sessions


@pytest.mark.parametrize(
    ("question", "expected_heading"),
    [
        (
            "me arrependi da compra, posso devolver?",
            "4.1 Direito de Arrependimento (Compras Online)",
        ),
        ("quais as regras de parcelamento no cartão", "3.1 Regras de Parcelamento"),
        ("o produto veio com defeito de fabricação", "4.2 Trocas por Defeito"),
        ("código de rastreamento do pedido", "5.3 Código de Rastreamento"),
    ],
)
async def test_hybrid_policy_search_finds_the_right_section(
    indexed: async_sessionmaker[AsyncSession], question: str, expected_heading: str
) -> None:
    hits = await SqlPolicyRetriever(indexed, EMBEDDER).search(question, k=3)

    assert expected_heading in [hit.heading for hit in hits]


async def test_embedding_stage_is_idempotent(indexed: async_sessionmaker[AsyncSession]) -> None:
    assert await ingest_embeddings(indexed, DATA_DIR, EMBEDDER, "hashing-test") is False


async def test_semantic_product_search_inside_filters(
    indexed: async_sessionmaker[AsyncSession],
) -> None:
    [query_vector] = await EMBEDDER.embed(["ukulele tenor"])
    results = await SqlProductReader(indexed).search(
        query_vector, ProductFilter(category_ids=(9,)), limit=3
    )

    assert results and "Tenor" in results[0].product.name
