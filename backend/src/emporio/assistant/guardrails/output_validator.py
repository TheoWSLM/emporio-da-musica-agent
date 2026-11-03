"""Checks every draft reply before the customer sees it."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from emporio.assistant.classification.ports import OutputClassifier
from emporio.assistant.guardrails.grounding import ungrounded_figures
from emporio.assistant.guardrails.leakage import personal_data_leaks, prompt_leaks

log = logging.getLogger(__name__)
REVIEW_FACTS_CHARS = 12000


class OutputValidator:
    """Deterministic checks always run (grounding, prompt leakage, personal data); the LLM review of the
    reply is optional and runs concurrently with them."""

    def __init__(
        self, *, system_prompt: str, canary: str, reviewer: OutputClassifier, review_enabled: bool
    ) -> None:
        self._system_prompt = system_prompt
        self._canary = canary
        self._reviewer = reviewer
        self._review_enabled = review_enabled

    async def problems(
        self,
        *,
        reply: str,
        customer_message: str,
        sources: Sequence[str],
        allowed_contacts: Sequence[str],
    ) -> list[str]:
        review = (
            asyncio.create_task(
                self._reviewer.review(
                    customer_message, reply, "\n".join(sources)[-REVIEW_FACTS_CHARS:]
                )
            )
            if self._review_enabled
            else None
        )
        problems = [
            f"valor sem fonte nas ferramentas: {v}"
            for v in ungrounded_figures(reply, sources, customer_message)
        ]
        problems += [
            f"vazamento: {p}"
            for p in prompt_leaks(reply, self._system_prompt, self._canary, sources)
        ]
        problems += [
            f"dado pessoal não verificado: {p}"
            for p in personal_data_leaks(reply, [*allowed_contacts, customer_message])
        ]
        if review is not None:
            try:
                problems += [f"revisão: {p}" for p in (await review).value.problems]
            except (
                Exception
            ) as exc:  # the optional review never blocks a reply that passed the code checks
                log.warning("output review failed: %s", exc)
        return problems
