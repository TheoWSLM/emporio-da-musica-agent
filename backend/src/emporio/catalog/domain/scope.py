"""Store scope rules (manual §1 and §7.1): the store sells only instruments, never accessories.

Also maps the words customers use to catalog categories (via each category's synonyms).
"""

from __future__ import annotations

import re
import unicodedata

from emporio.catalog.domain.models import Category

# Accessories the store explicitly does not sell (manual §1 and §7.1).
ACCESSORY_TERMS = (
    "corda",
    "cordas",
    "encordoamento",
    "palheta",
    "palhetas",
    "cabo",
    "cabos",
    "case",
    "cases",
    "bag",
    "capa",
    "pedal",
    "pedais",
    "pedaleira",
    "amplificador",
    "amplificadores",
    "amp",
    "caixa de som",
    "afinador",
    "estante",
    "suporte",
    "baqueta",
    "baquetas",
)
# Words that look like accessories but describe instruments ("cordas orquestrais", "violão de 7 cordas").
_INSTRUMENT_CONTEXT = re.compile(
    r"cordas? (orquestr|de nylon|de a[cç]o)|\d+ cordas|cordas? orquestrais"
)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def detect_accessory(text: str) -> str | None:
    normalized = _ascii(text)
    if _INSTRUMENT_CONTEXT.search(normalized):
        return None
    for term in ACCESSORY_TERMS:
        if re.search(rf"\b{re.escape(_ascii(term))}\b", normalized):
            return term
    return None


def resolve_categories(text: str, categories: list[Category]) -> list[Category]:
    normalized = _ascii(text)
    found = []
    for category in categories:
        terms = (category.name, *category.synonyms)
        if any(re.search(rf"\b{re.escape(_ascii(term))}\b", normalized) for term in terms):
            found.append(category)
    return found
