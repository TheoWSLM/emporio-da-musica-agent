"""Deterministic enrichment of the catalog: category synonyms and a readable search text per product."""

from __future__ import annotations

from collections.abc import Mapping

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

_SPEC_LABELS = {
    "top": "tampo",
    "back_sides": "fundo e laterais",
    "neck": "braço",
    "scale": "escala",
    "color": "cor",
    "body": "corpo",
    "shells": "cascos",
    "pieces": "peças",
    "hardware": "ferragens",
    "keys": "teclas",
    "type": "tipo",
    "polyphony": "polifonia",
}


def readable_specs(specs: Mapping[str, str]) -> list[str]:
    parts: list[str] = []
    for key, value in specs.items():
        if key == "strings":
            if value.isdigit():
                parts.append(f"{value} cordas")
            else:
                parts.append(
                    {"nylon": "cordas de nylon", "steel": "cordas de aço"}.get(value, value)
                )
        elif key == "electronics":
            parts.append(
                "eletroacústico (com captação)" if value == "yes" else "acústico (sem captação)"
            )
        elif key == "hardware" and value == "included":
            parts.append("ferragens incluídas")
        else:
            parts.append(f"{_SPEC_LABELS.get(key, key)}: {value}")
    return parts


def product_search_text(
    name: str, category: str, description: str, specs: Mapping[str, str]
) -> str:
    """The single text that represents a product for semantic search (one chunk per record)."""
    return f"{name}. Categoria: {category}. {description} Características: {'; '.join(readable_specs(specs))}."
