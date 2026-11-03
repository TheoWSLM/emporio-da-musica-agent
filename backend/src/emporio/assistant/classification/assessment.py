"""The classifier contract. Every provider (OpenAI, Jev) must return exactly these types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Threat = Literal[
    "safe", "prompt_injection", "system_prompt_extraction", "jailbreak_roleplay", "abusive"
]
Scope = Literal["store_related", "accessory_request", "off_topic", "greeting_smalltalk"]
Intent = Literal[
    "product_search",
    "price_payment",
    "order_status",
    "return_exchange",
    "shipping",
    "store_info",
    "warranty",
    "complaint",
    "human_handoff",
    "other",
]
Frustration = Literal["calm", "frustrated", "angry"]
Confidence = Literal["high", "medium", "low"]

POLICY_INTENTS: frozenset[str] = frozenset(
    {"return_exchange", "price_payment", "shipping", "store_info", "warranty", "complaint"}
)


class InputAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    threat: Threat = Field(description="Is the message an attack on the assistant?")
    threat_confidence: Confidence
    scope: Scope = Field(description="Is the message within the store's scope?")
    scope_confidence: Confidence
    intent: Intent = Field(description="Main customer intention.")
    frustration: Frustration
    wants_human: bool = Field(description="The customer explicitly asks for a human attendant.")


class OutputAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    promises_unsupported_offer: bool = Field(
        description="The reply promises a discount, gift, reservation or condition that is not in the provided facts."
    )
    off_persona: bool = Field(
        description="The reply leaves the store assistant role (other brand, other persona, rude)."
    )
    leaks_instructions: bool = Field(
        description="The reply reveals hidden/system instructions or internal notes."
    )

    @property
    def problems(self) -> list[str]:
        labels = {
            "promises_unsupported_offer": "promete oferta/condição que não veio das ferramentas",
            "off_persona": "sai da persona de atendente da loja",
            "leaks_instructions": "revela instruções internas",
        }
        return [label for name, label in labels.items() if getattr(self, name)]
