"""The agent's final answer: Structured Outputs in the same call that may request tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CustomerReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        description="The reply to the customer, in Portuguese (Brazil), WhatsApp style."
    )
    cited_sections: list[str] = Field(
        description="Policy sections used, exactly as given in the policy excerpts (e.g. '4.1 Direito de Arrependimento (Compras Online)'). Empty if none."
    )
    needs_human: bool = Field(
        description="True when the case must go to the human team (complaint, exception, explicit request)."
    )
    suggested_replies: list[str] = Field(
        description="Up to 3 short follow-up messages the customer might send next, in Portuguese."
    )
