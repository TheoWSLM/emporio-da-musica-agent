"""Deterministic grounding check: every figure in the reply must come from a verified source.

Checked figures: money (R$), percentages, installment counts (Nx) and day counts (N dias). Sources:
tool results of this turn, injected policy excerpts, the recent conversation and the customer's own
message. This enforces manual §7.1: never state prices, stock or deadlines without checking the system.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

_MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")
_PLAIN_NUMBER = re.compile(r"(?<![\d.,])(\d+(?:\.\d+)?)(?![\d])")
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")
_INSTALLMENTS = re.compile(r"\b(\d{1,2})\s?x\b", re.IGNORECASE)
_DAYS = re.compile(r"\b(\d{1,3})\s+dias?\b", re.IGNORECASE)


def _money(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for raw in _MONEY.findall(text):
        try:
            values.add(Decimal(raw.replace(".", "").replace(",", ".")).quantize(Decimal("0.01")))
        except InvalidOperation:
            continue
    return values


def _numbers(pattern: re.Pattern[str], text: str) -> set[Decimal]:
    return {Decimal(v.replace(",", ".")).normalize() for v in pattern.findall(text)}


def _plain(text: str) -> set[Decimal]:
    return {
        Decimal(v).normalize()
        for v in _PLAIN_NUMBER.findall(text.replace(".", "").replace(",", "."))
    }


def ungrounded_figures(reply: str, sources: Iterable[str], customer_text: str = "") -> list[str]:
    """`sources` are verified texts (tool results, policy excerpts, earlier replies). Bare numbers count as
    money only when the customer wrote them (e.g. "até 1000"), never from ids or stock counts."""
    corpus = "\n".join(sources)
    allowed_money = _money(corpus) | _money(customer_text)
    allowed_money |= {v.quantize(Decimal("0.01")) for v in _plain(customer_text)}
    problems = [f"R$ {v:,.2f}" for v in sorted(_money(reply) - allowed_money)]
    allowed_numbers = _plain(corpus) | _plain(customer_text)
    problems += [f"{v:f}%" for v in sorted(_numbers(_PERCENT, reply) - allowed_numbers)]
    problems += [f"{v:f}x" for v in sorted(_numbers(_INSTALLMENTS, reply) - allowed_numbers)]
    problems += [f"{v:f} dias" for v in sorted(_numbers(_DAYS, reply) - allowed_numbers)]
    return problems
