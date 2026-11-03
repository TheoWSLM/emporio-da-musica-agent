from pathlib import Path

import pytest
from pydantic import ValidationError

from emporio.ingestion.enrichment import product_search_text
from emporio.ingestion.loader import load_raw_dataset
from emporio.ingestion.quality import analyze
from emporio.ingestion.rows import CustomerIn, OrderIn, ProductIn

DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "raw"


def test_product_specs_json_string_is_parsed() -> None:
    row = ProductIn.model_validate(
        {
            "product_id": "95",
            "price_brl": "2199",
            "name": "Takamine GD20",
            "category_id": "5",
            "description": "Violão",
            "stock_quantity": "5",
            "status": "active",
            "specs": '{"strings":"steel","electronics":"no"}',
            "created_at": "2021-01-01",
        }
    )

    assert row.specs == {"strings": "steel", "electronics": "no"}


def test_order_blank_fields_become_none_and_payment_is_checked() -> None:
    base = {
        "order_id": "9",
        "customer_id": "6",
        "order_date": "2026-02-20",
        "status": "confirmed",
        "total_brl": "349.9",
        "payment_method": "credit_6x",
        "tracking_code": "",
        "estimated_delivery": "",
        "notes": "",
    }
    row = OrderIn.model_validate(base)
    assert row.tracking_code is None and row.estimated_delivery is None

    with pytest.raises(ValidationError):
        OrderIn.model_validate({**base, "payment_method": "cheque"})
    with pytest.raises(ValidationError):
        OrderIn.model_validate({**base, "tracking_code": "XX123"})


def test_customer_email_is_normalized() -> None:
    row = CustomerIn.model_validate(
        {
            "customer_id": "1",
            "name": "Ana",
            "phone": "(67) 99812-3456",
            "email": " Ana@Jmail.com ",
            "city": "CG",
        }
    )
    assert row.email == "ana@jmail.com"


def test_real_dataset_loads_without_errors() -> None:
    dataset = load_raw_dataset(DATA_DIR)

    assert dataset.errors == []
    assert (len(dataset.products), len(dataset.orders), len(dataset.order_items)) == (65, 20, 22)


def test_quality_report_flags_known_issues() -> None:
    titles = {f.title for f in analyze(load_raw_dataset(DATA_DIR))}

    assert "Active products without stock" in titles
    assert "Order totals differ from current prices" in titles
    assert "Several promotions for the same product" in titles


def test_search_text_is_readable() -> None:
    text = product_search_text(
        "Yamaha C40", "Violões", "Violão clássico.", {"strings": "nylon", "electronics": "no"}
    )

    assert "cordas de nylon" in text and "acústico (sem captação)" in text
