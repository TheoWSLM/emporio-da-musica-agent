"""The tools end to end over the real database (deterministic embedder, frozen clock)."""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.assistant.tools.context import ToolContext
from emporio.assistant.tools.registry import execute
from emporio.container import build_services
from emporio.ingestion.pipeline import ingest_embeddings
from emporio.knowledge.infrastructure.embedders import HashingEmbedder
from emporio.shared.clock import FixedClock

from .conftest import DATA_DIR

EMBEDDER = HashingEmbedder()


@pytest.fixture(scope="module")
async def ctx_factory(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[Any]:
    await ingest_embeddings(sessions, DATA_DIR, EMBEDDER, "hashing-test")
    clock = FixedClock(
        datetime(2026, 1, 22, 10, 0, tzinfo=ZoneInfo("America/Campo_Grande"))
    )  # Thursday
    services = build_services(sessions, EMBEDDER, clock)
    yield lambda: ToolContext(services=services)


async def call(ctx: ToolContext, name: str, **arguments: Any) -> dict[str, Any]:
    result = await execute(name, json.dumps(arguments), "call-1", ctx)
    return dict(json.loads(result.output))


async def test_search_violoes_up_to_1000(ctx_factory: Any) -> None:
    view = await call(
        ctx_factory(),
        "search_products",
        query=None,
        category="violão",
        min_price=None,
        max_price=1000,
        strings=None,
        electric=None,
        in_stock_only=True,
        limit=8,
    )

    assert view["results"]
    assert all(r["category"] == "Violões" for r in view["results"])
    assert "Giannini GF-3D Dreadnought Sunburst" not in {
        r["name"] for r in view["results"]
    }  # no stock


async def test_accessories_are_out_of_catalog(ctx_factory: Any) -> None:
    view = await call(
        ctx_factory(),
        "search_products",
        query="cordas para violão",
        category=None,
        min_price=None,
        max_price=None,
        strings=None,
        electric=None,
        in_stock_only=True,
        limit=5,
    )

    assert view["results"] == [] and "acessório" in view["note"]


async def test_takamine_price_with_pix(ctx_factory: Any) -> None:
    view = await call(ctx_factory(), "get_product", product_ref="Takamine GD20")

    assert view["product"]["name"] == "Takamine GD20 Dreadnought Natural"
    assert view["product"]["list_price"] == "R$ 2.199,00"
    assert view["product"]["pix_price"] == "R$ 2.089,05"
    assert [p["active"] for p in view["expired_promotions"]] == [False]  # expired 'Oferta Especial'


async def test_promotion_is_not_cumulative_with_pix(ctx_factory: Any) -> None:
    view = await call(ctx_factory(), "get_product", product_ref="90")

    assert view["product"]["promotion"]["discount"] == "18%"
    assert view["product"]["promotional_price"] == view["product"]["pix_price"] == "R$ 1.967,18"


async def test_discontinued_product_offers_alternatives(ctx_factory: Any) -> None:
    view = await call(ctx_factory(), "get_product", product_ref="Shelby SN-7C")

    assert view["product"]["availability"].startswith("descontinuado")
    assert view["alternatives"]


async def test_payment_options_explain_refused_installments(ctx_factory: Any) -> None:
    view = await call(
        ctx_factory(), "calculate_payment_options", product_id=81, amount=None, installments=12
    )

    # R$ 599,90: 6x = R$ 99,98 (>= R$ 80 for 4x-6x); 7x = R$ 85,70 (< R$ 100 for 7x-12x)
    assert view["installments"][-1]["count"] == 6
    assert "abaixo do mínimo" in view["requested_installments"]


async def test_order_status_requires_identity(ctx_factory: Any) -> None:
    ctx = ctx_factory()
    missing = await call(ctx, "get_order_status", order_id=8, email=None, phone=None)
    wrong = await call(ctx, "get_order_status", order_id=8, email="intruso@x.com", phone=None)
    unknown = await call(ctx, "get_order_status", order_id=999, email="intruso@x.com", phone=None)
    ok = await call(
        ctx, "get_order_status", order_id=8, email="anacarol.ferreira@coldmail.com", phone=None
    )

    assert missing["verified"] is False and wrong["verified"] is False
    assert wrong["message"] == unknown["message"]  # no order enumeration
    assert ok["status"] == "enviado (em trânsito)" and ok["tracking_code"] == "BRJL5544332BR"
    assert "anacarol.ferreira@coldmail.com" in ctx.verified_contacts


async def test_return_eligibility_uses_the_clock(ctx_factory: Any) -> None:
    view = await call(
        ctx_factory(),
        "check_return_eligibility",
        order_id=5,
        email="rafael.pereira@jmail.com",
        phone=None,
        reason="regret",
    )

    assert view["outcome"] == "elegível"  # delivered 18/01, clock at 22/01
    assert view["deadline"] == "25/01/2026"


async def test_store_status_and_shipping(ctx_factory: Any) -> None:
    status = await call(ctx_factory(), "get_store_status")
    shipping = await call(ctx_factory(), "estimate_shipping", city="Dourados", order_value=3000)

    assert status["is_open"] is True
    assert "CEP" in shipping["fee"]


async def test_policy_search_records_citations(ctx_factory: Any) -> None:
    ctx = ctx_factory()
    view = await call(ctx, "search_policies", query="me arrependi da compra, posso devolver?")

    assert any("4.1" in hit["section"] for hit in view["hits"])
    assert ctx.cited_sections


async def test_invalid_arguments_come_back_as_errors(ctx_factory: Any) -> None:
    view = await call(ctx_factory(), "get_order_status", order_id="abc")

    assert "invalid arguments" in view["error"]
