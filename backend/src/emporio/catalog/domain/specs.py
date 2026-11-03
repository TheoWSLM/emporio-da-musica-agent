"""Human-readable product specifications (PT-BR), shared by search indexing and the tool views."""

from __future__ import annotations

from collections.abc import Mapping

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
