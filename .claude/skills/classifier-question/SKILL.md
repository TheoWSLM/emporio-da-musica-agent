---
name: classifier-question
description: How to add or change a field of the input/output classifier (InputAssessment/OutputAssessment) so that the OpenAI adapter and the optional Jev adapter stay behaviourally identical. Use when changing guard, scope or intent classification.
---
# Changing the classifier contract

1. Edit the Pydantic contract in `assistant/classification/assessment.py` (labels as `Literal`).
2. OpenAI adapter (`classification/openai.py`): update `prompts/classifier.md` so every label is defined.
   Structured Outputs (strict) guarantees valid labels.
3. Jev adapter (`classification/jev.py`): add the matching Choice/Noul question; map probabilities to the
   same `confidence` buckets using the thresholds in config.
4. Decision function (`classification/decision.py`): route changes only here — it is provider-agnostic.
5. Contract tests (`tests/unit/assistant/test_classifier_contract.py`): the same cases must yield the same
   routes for both adapters (fakes feed each adapter's raw provider payload).
6. Add a golden-set case and run `make eval` (optionally `CLASSIFIER_PROVIDER=jev make eval`).
