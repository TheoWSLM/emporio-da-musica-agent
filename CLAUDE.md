# CLAUDE.md — Empório da Música agent

Customer-service agent for a fictional musical-instrument store (Artefact AI Engineer case).
Python 3.13 backend (FastAPI + LangGraph + OpenAI SDK), Postgres/pgvector, Vue 3 frontend.

## Architecture rules (non-negotiable)
- **Dependency rule:** `domain` ← `application` ← `infrastructure` ← `interfaces` (api, cli, assistant tools).
  Inner layers never import outer ones. Domain is plain Python: `@dataclass(frozen=True)`, enums, `Decimal`.
- **Pydantic v2 only at boundaries:** config, CSV rows, tool args/results, LLM structured outputs, API
  and SSE schemas, eval cases. Never inside `domain/`.
- **Business rules live in domain services**, never in tools, routes or prompts. Tools are thin adapters
  that validate input, call one use case and return a compact Pydantic view.
- **No model computes a business rule.** Prices, installments, return windows, shipping and store hours
  are always computed by code and exposed as tools.
- **Money is `Decimal`** (`emporio.shared.money.Money`); never floats.
- **Time comes from `Clock`** (`emporio.shared.clock`); never call `datetime.now()` in domain/application.
- The classifier is behind `InputClassifier`/`OutputClassifier` ports. The OpenAI adapter is the default;
  Jev is optional and must behave identically (same contract tests).

## Language
- Code, comments, commits, README: English.
- Everything the customer reads (prompts, canned replies, tool views shown to the customer): PT-BR.

## Layout
- `backend/src/emporio/<context>/{domain,application,infrastructure}` for catalog, orders, store,
  knowledge, conversation. `assistant/` holds the graph, tools, classification, guardrails, prompts.
- `data/raw/` original challenge data (read-only). `examples/` example conversations.
  `reports/` generated reports. `docs/` is local planning only and is git-ignored.

## Commands
- `make up` / `make down` / `make logs` — full stack via Docker Compose.
- `make lint` — ruff + mypy (strict). `make test-unit` — fast tests. `make test` — all but evals.
- `make eval` — golden set against real models. `make examples` — regenerate example conversations.

## Definition of done (per change)
1. Tests for the new behaviour (unit for domain rules; integration for repositories/retrieval).
2. `make lint` and `make test-unit` green.
3. Small Conventional Commit (`feat(catalog): ...`, `test(orders): ...`). Never squash or force-push.

Project skills in `.claude/skills/` describe the recipes for recurring changes.
