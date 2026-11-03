"""Classifier ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from emporio.assistant.classification.assessment import InputAssessment, OutputAssessment


@dataclass(frozen=True)
class Classified[T]:
    value: T
    provider: str
    latency_ms: int


class InputClassifier(Protocol):
    async def assess(
        self, message: str, previous_reply: str | None
    ) -> Classified[InputAssessment]: ...


class OutputClassifier(Protocol):
    async def review(
        self, message: str, reply: str, facts: str
    ) -> Classified[OutputAssessment]: ...
