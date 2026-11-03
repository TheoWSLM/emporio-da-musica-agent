"""Deterministic enrichment of the catalog: category synonyms and a readable search text per product."""

from __future__ import annotations

from collections.abc import Mapping

from emporio.catalog.domain.specs import readable_specs

# Words customers use for each category (category_id -> synonyms). Used for category filters in search.
CATEGORY_SYNONYMS: dict[int, tuple[str, ...]] = {
    1: ("guitarra", "guitarras", "guitarra elétrica", "guitarra eletrica"),
    2: ("baixo", "baixos", "contrabaixo elétrico", "baixo elétrico", "baixo eletrico"),
    3: ("bateria", "baterias", "percussão", "percussao"),
    4: (
        "teclado",
        "teclados",
        "piano",
        "piano digital",
        "sintetizador",
        "synth",
        "controlador midi",
    ),
    5: ("violão", "violões", "violao", "violoes", "violão clássico", "violão folk"),
    6: ("flauta", "clarinete", "saxofone", "sax", "oboé", "oboe", "sopro"),
    7: ("trompete", "trombone", "tuba", "trompa", "metais"),
    8: ("violino", "viola", "violoncelo", "cello", "contrabaixo acústico", "orquestral"),
    9: ("ukulele", "ukuleles", "uke", "ukulelê"),
}


def product_search_text(
    name: str, category: str, description: str, specs: Mapping[str, str]
) -> str:
    """The single text that represents a product for semantic search (one chunk per record)."""
    return f"{name}. Categoria: {category}. {description} Características: {'; '.join(readable_specs(specs))}."
