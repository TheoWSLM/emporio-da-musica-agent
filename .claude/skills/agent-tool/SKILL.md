---
name: agent-tool
description: Recipe for creating or changing an LLM tool used by the customer-service agent (strict Pydantic args, compact view output, registration, eval case). Use when the agent needs a new capability or a tool's contract changes.
---
# Creating an agent tool

1. **Args model** in `assistant/tools/schemas.py`: Pydantic v2, `model_config = ConfigDict(extra="forbid")`,
   every field described (`Field(description=...)`) in English, enums as `Literal`. Optional fields are
   `X | None` — strict function calling makes every field required-but-nullable.
2. **View model**: the result the LLM reads. Keep it compact and *ready to communicate* (prices already
   computed, statuses already translated to PT-BR labels). Every number the agent may quote must be in the
   view — the grounding validator only accepts figures that appear in tool results.
3. **Adapter** in `assistant/tools/`: validate args, call exactly one use case, map to the view. No business
   rules here. Domain errors become a structured `{"error": ...}` view, never an exception to the model.
4. **Register** in `assistant/tools/registry.py` (name, description written for the model, args, handler).
5. **Prompt**: one line in the tool guide of `assistant/prompts/system.md` saying *when* to use it.
6. **Eval**: add at least one case to `tests/evals/golden_set.yaml` with `expected_tools`.
