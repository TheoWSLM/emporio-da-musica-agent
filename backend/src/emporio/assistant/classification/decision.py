"""The single, provider-agnostic routing decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from emporio.assistant.classification.assessment import POLICY_INTENTS, InputAssessment
from emporio.assistant.guardrails.heuristics import HeuristicResult


class Route(StrEnum):
    BLOCK = "block"
    OFF_TOPIC = "off_topic"
    PROCEED = "proceed"


@dataclass(frozen=True)
class Decision:
    route: Route
    heightened_caution: bool
    prefetch_policies: bool
    reason: str


def decide(assessment: InputAssessment, heuristics: HeuristicResult) -> Decision:
    prefetch = assessment.intent in POLICY_INTENTS
    if heuristics.strong:
        return Decision(Route.BLOCK, True, False, "heuristic: known injection pattern")
    attack = assessment.threat != "safe"
    if attack and assessment.threat_confidence == "high":
        return Decision(Route.BLOCK, True, False, f"classifier: {assessment.threat}")
    caution = attack or bool(heuristics.flags)
    if assessment.scope == "off_topic" and assessment.scope_confidence == "high" and not caution:
        return Decision(Route.OFF_TOPIC, False, False, "classifier: off topic")
    reason = f"caution: {assessment.threat}" if caution else "ok"
    return Decision(Route.PROCEED, caution, prefetch, reason)
