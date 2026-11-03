"""Zero-cost input heuristics that run before any model.

A strong match blocks immediately; a weak match is only a signal for the decision function.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

_STRONG = [
    r"ignor\w* (todas |as |suas |all |the |previous |anteriores |)*(instru[cç][oõ]es|instructions|regras|rules)",
    r"(mostre|revele|repita|imprima|show|reveal|print|repeat)\w* (o |seu |your |the )*(prompt|instru[cç][oõ]es (do sistema|internas)|system prompt)",
    r"system prompt",
    r"prompt (de|do) sistema",
    r"\b(you are now|voc[eê] agora [eé]|a partir de agora voc[eê] [eé])\b",
    r"\b(DAN|developer mode|modo desenvolvedor|jailbreak)\b",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
    r"^\s*(system|assistant)\s*:",
]
_WEAK = [
    r"\bfinja\b|\bpretend\b|\broleplay\b|\binterprete um\b",
    r"\b(desconto|discount) de (\d{2,3})\s*%",
    r"\b(esque[cç]a|forget)\b",
]
_BASE64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


@dataclass(frozen=True)
class HeuristicResult:
    strong: bool
    flags: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    """NFKC folds look-alike characters (fullwidth letters, ligatures) used to dodge filters."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[​-‏⁠﻿]", "", text)


def _decodes_to_text(candidate: str) -> bool:
    try:
        decoded = base64.b64decode(candidate, validate=True).decode("utf-8")
    except Exception:
        return False
    return sum(ch.isprintable() for ch in decoded) / max(len(decoded), 1) > 0.9


def inspect(message: str) -> HeuristicResult:
    text = normalize(message).lower()
    flags = [
        f"strong:{p[:40]}" for p in _STRONG if re.search(p, text, re.IGNORECASE | re.MULTILINE)
    ]
    strong = bool(flags)
    flags += [f"weak:{p[:40]}" for p in _WEAK if re.search(p, text, re.IGNORECASE)]
    if any(_decodes_to_text(m) for m in _BASE64.findall(message)):
        flags.append("weak:base64_payload")
    return HeuristicResult(strong=strong, flags=flags)
