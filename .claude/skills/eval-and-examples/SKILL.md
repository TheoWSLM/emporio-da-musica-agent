---
name: eval-and-examples
description: How to run the golden-set evaluation, read the report and regenerate the example conversations delivered with the case. Use after changing prompts, tools, retrieval or the classifier.
---
# Evals and example conversations

- `make eval` runs `tests/evals/golden_set.yaml` against the real models and writes `reports/eval-report.md`
  (tool-selection accuracy, required/forbidden facts, classifier verdicts, latency p50/p95).
- `CLASSIFIER_PROVIDER=jev make eval` produces the Jev column of the case-study table (needs
  `TYPESAFE_API_KEY`); results are merged into the same report.
- A regression is any case that passed before and fails now: fix the cause (tool view, prompt, retrieval),
  never loosen the expectation without writing down why.
- `make examples` replays the scripted conversations in `examples/scripts.yaml` and rewrites
  `examples/conversations/*.md` (PT-BR transcript + English summary + tools used). Uses
  `APP_REFERENCE_DATE` from the script so return-window examples are reproducible.
