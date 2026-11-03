"""Cross-table data-quality checks. The output is rendered as reports/data-quality.md."""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from emporio.ingestion.loader import RawDataset


@dataclass(frozen=True)
class Finding:
    title: str
    detail: str
    treatment: str


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def analyze(dataset: RawDataset) -> list[Finding]:
    findings: list[Finding] = []
    products = {p.product_id: p for p in dataset.products}
    customers = {c.customer_id: c for c in dataset.customers}
    categories = {c.category_id: c for c in dataset.categories}

    for error in dataset.errors:
        findings.append(
            Finding(
                f"Invalid row in {error.file}:{error.line}",
                error.message,
                "Row skipped at ingestion.",
            )
        )

    per_category = Counter(
        categories[p.category_id].name if p.category_id in categories else "?"
        for p in products.values()
    )
    empty = [c.name for c in categories.values() if per_category[c.name] == 0]
    findings.append(
        Finding(
            "Uneven catalog coverage",
            ", ".join(f"{name}: {count}" for name, count in per_category.most_common())
            + (f". Categories without products: {', '.join(empty)}." if empty else "."),
            "Searches in empty categories answer honestly that there is nothing in the catalog.",
        )
    )

    status_count = Counter(p.status for p in products.values())
    special = [f"{p.product_id} ({p.status})" for p in products.values() if p.status != "active"]
    findings.append(
        Finding(
            "Non-active products",
            f"Status distribution: {dict(status_count)}. Non-active: {', '.join(special)}.",
            "Discontinued and coming-soon products are never offered for sale; the agent suggests similar in-stock items.",
        )
    )

    zero_active = [
        str(p.product_id)
        for p in products.values()
        if p.status == "active" and p.stock_quantity == 0
    ]
    if zero_active:
        findings.append(
            Finding(
                "Active products without stock",
                f"Products {', '.join(zero_active)} are 'active' with stock_quantity = 0.",
                "Availability is derived from stock, not from status: shown as temporarily out of stock.",
            )
        )

    by_product: dict[int, list[Decimal]] = defaultdict(list)
    active_by_product: dict[int, list[Decimal]] = defaultdict(list)
    for promo in dataset.promotions:
        by_product[promo.product_id].append(promo.discount_percent)
        if promo.is_active:
            active_by_product[promo.product_id].append(promo.discount_percent)
    repeated = {pid: v for pid, v in by_product.items() if len(v) > 1}
    if repeated:
        findings.append(
            Finding(
                "Several promotions for the same product",
                "; ".join(
                    f"product {pid}: {len(v)} promotions" for pid, v in sorted(repeated.items())
                ),
                "Only active promotions count; if several were active, the largest discount would win.",
            )
        )
    multi_active = [pid for pid, v in active_by_product.items() if len(v) > 1]
    findings.append(
        Finding(
            "Active promotions",
            f"{sum(len(v) for v in active_by_product.values())} active promotions on products "
            f"{', '.join(map(str, sorted(active_by_product)))}"
            + (
                f"; more than one active on {multi_active}."
                if multi_active
                else "; at most one active per product."
            ),
            "Promotions have no validity dates: `is_active` is taken as the source of truth.",
        )
    )

    orphan_promos = [p.promotion_id for p in dataset.promotions if p.product_id not in products]
    orphan_items = [
        f"{i.order_id}->{i.product_id}" for i in dataset.order_items if i.product_id not in products
    ]
    orphan_orders = [o.order_id for o in dataset.orders if o.customer_id not in customers]
    if orphan_promos or orphan_items or orphan_orders:
        findings.append(
            Finding(
                "Broken references",
                f"promotions {orphan_promos}, order items {orphan_items}, orders {orphan_orders}",
                "Rows with broken references are skipped at ingestion.",
            )
        )

    items_by_order: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for item in dataset.order_items:
        items_by_order[item.order_id].append((item.product_id, item.quantity))
    mismatches: list[str] = []
    non_sellable: list[str] = []
    for order in dataset.orders:
        items = items_by_order.get(order.order_id, [])
        if not items:
            mismatches.append(f"order {order.order_id}: no items")
            continue
        expected = sum(
            (products[pid].price_brl * qty for pid, qty in items if pid in products), Decimal(0)
        )
        if expected != order.total_brl:
            mismatches.append(
                f"order {order.order_id}: total {order.total_brl} vs items x current price {expected}"
            )
        for pid, _ in items:
            if pid in products and products[pid].status != "active":
                non_sellable.append(
                    f"order {order.order_id} ({order.status}) has product {pid} ({products[pid].status})"
                )
    if mismatches:
        findings.append(
            Finding(
                "Order totals differ from current prices",
                "; ".join(mismatches),
                "The order total is historical (prices change): it is shown as stored and never recalculated.",
            )
        )
    if non_sellable:
        findings.append(
            Finding(
                "Orders containing products that are not for sale today",
                "; ".join(non_sellable),
                "Kept as historical facts; documented as a data inconsistency.",
            )
        )

    findings.append(
        Finding(
            "No receipt date on orders",
            "Orders only have `estimated_delivery`; return windows (§4.1, §4.3) count from the receipt date.",
            "For delivered orders the estimated delivery date is assumed to be the receipt date.",
        )
    )
    latest = max(o.order_date for o in dataset.orders)
    findings.append(
        Finding(
            "Historical data",
            f"The most recent order is from {latest:%Y-%m-%d}; with today's date every return window is closed.",
            "The business clock accepts APP_REFERENCE_DATE so that return scenarios can be demonstrated.",
        )
    )

    first_last: dict[str, list[str]] = defaultdict(list)
    for customer in customers.values():
        parts = _ascii(customer.name).split()
        first_last[f"{parts[0]} {parts[-1]}"].append(customer.name)
    similar = [names for names in first_last.values() if len(names) > 1]
    prefix_dupes = [
        (a.name, b.name)
        for a in customers.values()
        for b in customers.values()
        if (a.customer_id < b.customer_id and _ascii(a.name).startswith(_ascii(b.name) + " "))
        or (a.customer_id < b.customer_id and _ascii(b.name).startswith(_ascii(a.name) + " "))
    ]
    if similar or prefix_dupes:
        detail = "; ".join(" / ".join(n) for n in similar)
        if prefix_dupes:
            detail += ("; " if detail else "") + "; ".join(f"{a} / {b}" for a, b in prefix_dupes)
        findings.append(
            Finding(
                "Customers with near-duplicate names",
                detail,
                "Identity is verified by e-mail or phone, never by name.",
            )
        )
    return findings


def render_markdown(dataset: RawDataset, findings: list[Finding]) -> str:
    counts = (
        f"| categories | products | promotions | customers | orders | order items |\n"
        f"|---|---|---|---|---|---|\n"
        f"| {len(dataset.categories)} | {len(dataset.products)} | {len(dataset.promotions)} | "
        f"{len(dataset.customers)} | {len(dataset.orders)} | {len(dataset.order_items)} |\n"
    )
    body = "\n".join(
        f"### {i}. {f.title}\n- **Finding:** {f.detail}\n- **Treatment:** {f.treatment}\n"
        for i, f in enumerate(findings, start=1)
    )
    manual = (
        "### Store manual (PDF)\n"
        "- **Finding:** the e-mail appears as `contato@emporiodamusica.com.br` and `contato@empóriodamusica.com.br`; "
        "§1.2 lists (67) 3341-4444 as phone/WhatsApp while §7 lists (67) 3321-4500 as the WhatsApp channel.\n"
        "- **Treatment:** the unaccented e-mail is used; both phone numbers are given as the manual states them.\n"
        '- **Finding:** §3.1 says installments up to 3x have "no minimum, except below R$ 50,00".\n'
        "- **Treatment:** interpreted as a R$ 50,00 minimum installment for 2x–3x.\n"
    )
    return (
        "# Data quality report\n\n"
        "Generated by `emporio data-report` from `data/raw/` (every row is validated with Pydantic before "
        "ingestion).\n\n"
        f"## Volumes\n\n{counts}\n## Findings and treatment\n\n{body}\n{manual}"
    )
