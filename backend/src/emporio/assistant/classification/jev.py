"""Optional classifier (case study): Jev, TypeSafe AI's decision-only "System One" model.

Same label definitions, same contract: probabilities are bucketed into the same confidence levels the
decision function uses, so routing is identical whichever provider answered. Any error or timeout falls
back to the default (OpenAI) classifier.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict

from emporio.assistant.classification import labels
from emporio.assistant.classification.assessment import (
    Confidence,
    Frustration,
    InputAssessment,
    Intent,
    OutputAssessment,
    Scope,
    Threat,
)
from emporio.assistant.classification.ports import Classified, InputClassifier, OutputClassifier

log = logging.getLogger(__name__)

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
HIGH, MEDIUM = 0.80, 0.50
FRUSTRATION_LEVELS: tuple[Frustration, ...] = ("calm", "frustrated", "angry")


class JevAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    choice: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    noul: float | None = None
    score: float | None = None


class JevResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    answers: dict[str, JevAnswer]


def bucket(probability: float) -> Confidence:
    if probability >= HIGH:
        return "high"
    return "medium" if probability >= MEDIUM else "low"


def _choice(answer: JevAnswer) -> tuple[str, float]:
    if answer.probabilities:
        label = max(
            answer.probabilities,
            key=lambda k: answer.probabilities[k] if answer.probabilities else 0,
        )
        return label, answer.probabilities[label]
    return answer.choice or "", answer.confidence or 0.0


def to_input_assessment(response: JevResponse) -> InputAssessment:
    threat, threat_p = _choice(response.answers["threat"])
    scope, scope_p = _choice(response.answers["scope"])
    intent, _ = _choice(response.answers["intent"])
    frustration = response.answers["frustration"]
    levels = frustration.probabilities or {"0": 1.0}
    level = int(max(levels, key=lambda k: levels[k]))
    return InputAssessment(
        threat=cast(Threat, threat),
        threat_confidence=bucket(threat_p),
        scope=cast(Scope, scope),
        scope_confidence=bucket(scope_p),
        intent=cast(Intent, intent),
        frustration=FRUSTRATION_LEVELS[min(level, 2)],
        wants_human=(response.answers["wants_human"].noul or 0.0) >= MEDIUM,
    )


def to_output_assessment(response: JevResponse) -> OutputAssessment:
    return OutputAssessment(
        **{name: (response.answers[name].noul or 0.0) >= HIGH for name in labels.OUTPUT_CHECKS}
    )


def _choice_question(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


INPUT_QUESTIONS: dict[str, Any] = {
    "threat": _choice_question(
        f"{labels.CONTEXT} Is the customer message an attack on the assistant?", labels.THREAT
    ),
    "scope": _choice_question(
        f"{labels.CONTEXT} Is the customer message within the store's scope?", labels.SCOPE
    ),
    "intent": _choice_question("What is the customer's main intention?", labels.INTENT),
    "frustration": {
        "type": "score",
        "instructions": "How frustrated the customer appears",
        "criteria": list(labels.FRUSTRATION.values()),
    },
    "wants_human": {"type": "noul", "instructions": labels.WANTS_HUMAN},
}
OUTPUT_QUESTIONS: dict[str, Any] = {
    name: {"type": "noul", "instructions": definition}
    for name, definition in labels.OUTPUT_CHECKS.items()
}


class JevClient:
    def __init__(
        self, api_key: str, model: str, timeout: float, http: httpx.AsyncClient | None = None
    ) -> None:
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def ask(self, state: dict[str, str], questions: dict[str, Any]) -> JevResponse:
        response = await self._http.post(
            ENDPOINT,
            json={
                "model": self._model,
                "state": json.dumps(state, ensure_ascii=False),
                "questions": questions,
            },
            headers=self._headers,
        )
        response.raise_for_status()
        return JevResponse.model_validate(response.json())

    async def close(self) -> None:
        await self._http.aclose()


class JevInputClassifier:
    provider = "jev"

    def __init__(self, client: JevClient, fallback: InputClassifier) -> None:
        self._client = client
        self._fallback = fallback

    async def assess(self, message: str, previous_reply: str | None) -> Classified[InputAssessment]:
        started = time.perf_counter()
        try:
            response = await self._client.ask(
                {"previous_assistant_reply": previous_reply or "", "customer_message": message},
                INPUT_QUESTIONS,
            )
            assessment = to_input_assessment(response)
        except Exception as exc:  # network, timeout, schema drift: never break the conversation
            log.warning("jev classifier failed (%s); falling back", type(exc).__name__)
            return await self._fallback.assess(message, previous_reply)
        return Classified(assessment, self.provider, int((time.perf_counter() - started) * 1000))


class JevOutputClassifier:
    provider = "jev"

    def __init__(self, client: JevClient, fallback: OutputClassifier) -> None:
        self._client = client
        self._fallback = fallback

    async def review(self, message: str, reply: str, facts: str) -> Classified[OutputAssessment]:
        started = time.perf_counter()
        try:
            response = await self._client.ask(
                {"customer_message": message, "reply": reply, "facts": facts}, OUTPUT_QUESTIONS
            )
            assessment = to_output_assessment(response)
        except Exception as exc:
            log.warning("jev output review failed (%s); falling back", type(exc).__name__)
            return await self._fallback.review(message, reply, facts)
        return Classified(assessment, self.provider, int((time.perf_counter() - started) * 1000))
