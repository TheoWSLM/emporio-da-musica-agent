"""Institutional store data (store manual §1.2 and §7). Structured reference data, not retrieved by RAG."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreInfo:
    name: str
    legal_name: str
    tagline: str
    address: str
    phone: str
    whatsapp: str
    email: str
    founded: int
    sells: str
    does_not_sell: tuple[str, ...]


# The manual lists two phone numbers: (67) 3341-4444 as "Telefone / WhatsApp" (§1.2) and
# (67) 3321-4500 as the WhatsApp channel (§7). Both are kept as the manual states them.
# The e-mail appears with and without an accent; the unaccented form is the valid one.
EMPORIO = StoreInfo(
    name="Empório da Música",
    legal_name="Empório da Música Instrumentos Musicais Ltda.",
    tagline="Sua música começa aqui.",
    address="Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    phone="(67) 3341-4444",
    whatsapp="(67) 3321-4500",
    email="contato@emporiodamusica.com.br",
    founded=2008,
    sells=(
        "instrumentos musicais: guitarras, baixos, violões, baterias e percussão, teclados e pianos, "
        "sopros (madeiras e metais), cordas orquestrais e ukuleles"
    ),
    does_not_sell=(
        "cordas",
        "palhetas",
        "cabos",
        "cases",
        "pedais",
        "amplificadores",
    ),
)
