# Empório da Música — customer-service agent

**Lia** is a text-message assistant for Empório da Música, a fictional musical-instrument store in
Campo Grande/MS. She answers customers in Brazilian Portuguese, knows when to query the store's data
(prices, stock, orders, promotions) and when to look up its policies (returns, payment, shipping,
warranty, hours), and handles out-of-scope requests and manipulation attempts safely.

- **Live demo:** **https://council-genes-marriage-messaging.trycloudflare.com** (no setup needed; rate-limited, see [Live demo](#live-demo)).
- **Run locally:** `cp .env.example .env`, set `OPENAI_API_KEY`, then `make up` and open http://127.0.0.1:18082.
- **Example conversations:** [`examples/conversations/`](examples/conversations/). The non-trivial one is
  [return after regret](examples/conversations/03-return-after-regret.md).
- **Evaluation:** [`reports/eval-report.md`](reports/eval-report.md). 28/28 golden-set cases pass with either classifier.

![Chat and backstage panel](assets/screenshot.png)

---

## Contents

1. [Quickstart](#quickstart)
2. [Live demo](#live-demo)
3. [Architecture at a glance](#architecture-at-a-glance)
4. [Technical decisions](#technical-decisions)
5. [Data handling and assumptions](#data-handling-and-assumptions)
6. [Evaluation](#evaluation)
7. [Case study: a pluggable classifier (OpenAI vs. Jev)](#case-study-a-pluggable-classifier-openai-vs-jev)
8. [Example conversations](#example-conversations)
9. [Known limitations and what I would do with more time](#known-limitations-and-what-i-would-do-with-more-time)
10. [AI-assisted development](#ai-assisted-development)
11. [Repository map and commands](#repository-map-and-commands)

---

## Quickstart

Requirements: Docker with Compose v2 and `make`. The only required credential is an OpenAI API key.

```bash
cp .env.example .env          # then set OPENAI_API_KEY=sk-...
make up                       # builds and starts everything, then prints the URL
```

`make up` starts `postgres` (pgvector) and then runs `migrate` (Alembic) and `ingest`. The ingestion validates
the CSVs, chunks and embeds the policy manual and the products, and is idempotent. After that it starts
`api` (FastAPI) and the edge (Caddy, which serves the Vue UI and proxies `/api`). Open **http://127.0.0.1:18082**.

| Command | What it does |
|---|---|
| `make chat` | Talk to Lia in the terminal (shows the classifier reading and the tool calls) |
| `make test` | Unit, graph and integration tests on a disposable Postgres. No paid API calls |
| `make lint` | ruff + ruff format + mypy `--strict` |
| `make eval` | Golden-set evaluation against the real models, written to `reports/` |
| `make examples` | Regenerates the example conversations from `examples/scripts.yaml` |
| `make data-report` | Regenerates [`reports/data-quality.md`](reports/data-quality.md) |
| `make down` / `make reset` | Stop the stack / also delete the database (it is rebuilt on the next `up`) |

Optional settings in `.env`:
- **`TYPESAFE_API_KEY`** switches the input classifier to Jev (see the [case study](#case-study-a-pluggable-classifier-openai-vs-jev)).
  Without it, everything works the same through the OpenAI classifier.
- **`APP_REFERENCE_DATE=2026-01-22`** pins the business calendar. The sample orders end in March 2026, so
  with today's date every return window is already closed. Pinning the date lets you see a return accepted
  (order 5, e-mail `rafael.pereira@jmail.com`).
- The model names (`AGENT_MODEL`, `CLASSIFIER_MODEL`, `EMBEDDING_MODEL`) and the demo limits are also configurable.

The interactive API docs are at http://127.0.0.1:18082/api/docs.

## Live demo

**https://council-genes-marriage-messaging.trycloudflare.com**

- **Where it runs:** the same Compose stack, on my home server, with my API keys, so the agent can be tried
  without any setup. It is published through a Cloudflare Quick Tunnel (a random `trycloudflare.com` address,
  no domain needed). The edge never opens a port on the router, and the app's containers are isolated from the
  other apps on the host.
- **Protection of the keys:** per-IP and per-conversation limits, a daily cap and a 2,000-character message limit.
  Requests over a limit get HTTP 429. The client IP comes from Cloudflare's header, so each visitor has their
  own limit.
- **Business date:** it is the real one, so the sample orders' return windows are already closed. To see a
  return accepted, run locally with `APP_REFERENCE_DATE=2026-01-22`.
- **If the link is down:** `make up` gives the same result locally.

The deployment procedure, the audit and the scripts are in [`deploy/homeserver/`](deploy/homeserver/OPERATIONS.md).

---

## Architecture at a glance

```mermaid
flowchart LR
    UI["Vue 3 chat<br/>+ backstage panel"] -- "POST /api/…/messages<br/>(SSE stream)" --> EDGE["Caddy edge"] --> API["FastAPI"]
    API --> G
    subgraph G["LangGraph — one turn"]
        direction LR
        H[load_history] --> C["classify_input<br/>heuristics + classifier"]
        H --> P["policy_prefetch<br/>hybrid search"]
        C --> R{route}
        P --> R
        R -- "blocked / off-topic" --> K[canned reply]
        R -- proceed --> A["agent<br/>gpt-6.1-terra"]
        A <-- "parallel calls" --> T["9 typed tools"]
        A --> V["validate_output<br/>grounding · leaks · PII"]
        V -- "reject once" --> A
        V --> S[persist]
        K --> S
    end
    T --> UC["use cases → domain rules<br/>(pricing, installments, returns, hours, shipping)"]
    UC --> DB[("PostgreSQL 16<br/>pgvector · pg_trgm · FTS")]
    P --> DB
```

There are three separate roles:

- **A classifier** that only *decides*: is the message an attack, is it in scope, what is the intent, is the
  customer frustrated. It answers a fixed Pydantic contract with Structured Outputs.
- **The agent**, which *reasons and talks*: it chooses which tools to call and writes the reply.
- **Deterministic code**, which *knows the business*. Prices, PIX discount, installment minimums, return
  windows, shipping fees and opening hours are domain functions with unit tests. No model ever computes a
  business fact.

The code follows DDD bounded contexts (`catalog`, `orders`, `store`, `knowledge`, `conversation`) plus the
`assistant` application layer. Each context has the layers `domain` (plain Python) ← `application` (use cases
and ports) ← `infrastructure` (SQLAlchemy, pgvector, OpenAI). The only place that wires adapters to ports is
[`container.py`](backend/src/emporio/container.py).

---

## Technical decisions

Each decision follows the same format: **what** I chose, **why** it fits this case, the **alternatives** I
considered and the **trade-off** I accepted.

### 1. Function calling for data, RAG for policies (no text-to-SQL, no RAG over the CSVs)
- **Why:** prices, stock and order status must be exact and need numeric filters ("violões até R$1000").
  Typed tools return exactly that. The policy manual is prose and tables, which is where semantic retrieval
  helps.
- **Alternatives:**
  - A SQL agent: the model writes SQL, which risks wrong queries and SQL injection, and the result still has
    to be interpreted.
  - RAG over the tables: embeddings are bad at "≤ 1000" and at exact stock counts.
- **Trade-off:** a new kind of question needs a new tool. That is deliberate: it keeps what the agent can
  touch explicit and testable.

### 2. One agent, no supervisor
- **Why:**
  - The domain is small and coherent: 9 tools, one audience, one tone.
  - Customers mix data and policy in one message ("o GD20 tá em promoção e dá pra fazer em 10x?"). A single
    agent answers that in one round of parallel tool calls. A supervisor would hand off between agents and
    lose context.
  - A supervisor costs at least one more model call per turn and adds a routing failure mode.
  - The routing that matters here (block, off-topic, intent) is a *classification* problem, so it is solved by
    a cheap classifier node in parallel with retrieval, not by a generative supervisor.
- **When I would switch:** separate domains maintained by different teams (technical assistance, B2B sales),
  more than about 20 tools, or domains that need different models or policies.
- **Trade-off:** a single system prompt has to cover every situation. It stays readable because the rules
  live in the tools.

### 3. The business rules live in deterministic tools
- **Why:** the manual says "never give prices, stock or deadlines without checking the system". The tools
  return views that are **ready to communicate**: money already formatted (`R$ 2.089,05`), statuses already in
  Portuguese, the installment refusal already explained ("em 10x a parcela seria R$ 59,99, abaixo do mínimo de
  R$ 100,00").
- **Edge cases covered by unit tests:**
  - PIX 5% does not stack with promotions.
  - The best *active* promotion wins.
  - Installment minimums of R$50, R$80 and R$100 depending on the number of installments.
  - Combined payment only above R$2,000.
  - Regret: 7 days from receipt. Defect: 30 days from purchase, then the manufacturer warranty (legal
    warranty: 90 days).
  - The exclusions in §4.4.
  - Opening hours, including Saturdays and fixed national holidays.
  - Metro-area shipping vs. a quote by ZIP code.
- **LGPD:** order data is disclosed only after an identity check (order number plus e-mail or phone). Order
  "not found" and "wrong e-mail" produce the *same* answer, so the bot cannot be used to discover which order
  numbers exist.
- **Trade-off:** more code than a "smart prompt", but every rule can be read and tested.

### 4. Retrieval: Postgres + pgvector, hybrid search, chunking by document type
- **One database for everything:** relational data, vectors, full-text search and conversation history.
  - That means one less service than with Qdrant or Chroma, migrations through Alembic, and **SQL filters and
    vector ranking in the same query** (essential for the catalog).
  - The documents are static, so embeddings are computed **once at ingestion**. The ingestion is keyed on a
    hash of the data, the chunking version and the embedding model. At runtime only the question is embedded.
- **Chunking by document type:**
  - **Policy manual (PDF):** *structural* chunking, one chunk per subsection carrying its heading path
    (`4. Política de Trocas… > 4.1 Direito de Arrependimento`).
    - Each subsection is one complete rule. A fixed-size split would separate a rule from its exception.
    - Headings are detected from the **layout** (14 pt for sections, 12 pt for subsections), not from regexes,
      which would confuse the numbered list in §7.2 with sections.
    - Tables are kept whole as Markdown, and the running header and footer are removed.
    - Sections above ~500 tokens fall back to a *semantic* split at the weakest link between paragraphs. The
      current manual never triggers it.
  - **Products:** one chunk per record (name, category, description, readable specs). The embedding is stored
    on the product row, and the filters stay in SQL.
  - **Orders, customers, promotions:** SQL only. Vectorising transactional data would be a design error and a
    privacy risk.
- **Hybrid ranking:**
  - Policies: pgvector cosine plus Portuguese full-text search, fused with Reciprocal Rank Fusion.
  - Product names: `pg_trgm` (handles "takamine gd 20", typos and ambiguity — "Martin D-28" matches the D-28
    and the D-28E, and the agent asks which one).
- **An honest note:** the 8-page manual would fit in the prompt. I still used RAG because it lets the agent
  **cite the section**, it scales to a bigger manual, and with prefetch (decision 7) it costs no extra
  model call.

### 5. Models: `gpt-6.1-terra` for the agent, `gpt-6-luna` for classification, `text-embedding-3-small`
- **Why:**
  - The agent needs reliable multi-step function calling and natural Brazilian Portuguese. `gpt-6.1-terra` has
    the best cost/benefit for that (US$ 1 / 5 per million tokens).
  - Classification and the LLM-as-judge are short, closed tasks, so the lightest model is enough
    (`gpt-6-luna`, US$ 0.10 / 0.50).
  - Embeddings use the same API key, so there is no local model to download (smaller image).
- **Measured:** `reasoning_effort=none` gave the same answers as `low` at 20–35% lower latency, so it is the
  default.
- **Alternatives:** a larger model (`gpt-6.1-sol`) can be set through `.env`, but the evaluation did not show a
  need for it. Local models were left out to keep the evaluator's setup to one API key.

### 6. Structured Outputs and Pydantic v2 at the boundaries, a plain-Python domain
Pydantic validates everything that **crosses a boundary**; the domain stays framework-free (frozen
dataclasses, enums, `Decimal`):

| Boundary | Pydantic model | Mechanism |
|---|---|---|
| Configuration | `Settings` | `pydantic-settings`, `SecretStr` for keys |
| CSV rows | `ProductIn`, `OrderIn`, … | Validators parse the specs JSON, `credit_12x`, tracking codes and e-mails; bad rows go to the quality report |
| Tool arguments | `SearchProductsArgs`, … | **Strict function calling** (the JSON schema is guaranteed), plus revalidation; errors return to the model as data |
| Tool results | `ProductView`, `ReturnEligibilityView`, … | What the model reads. The same values feed the grounding check and the UI |
| Classifier | `InputAssessment` / `OutputAssessment` | **Structured Outputs** (strict). It is also the contract the Jev adapter must meet |
| Final answer | `CustomerReply {message, cited_sections, needs_human, suggested_replies}` | Structured Outputs **in the same call that may request tools**: the model either calls tools or returns the JSON |
| API and SSE | `SendMessageRequest`, a discriminated union of events | FastAPI and a `TypeAdapter` validate every event before it is sent |
| Evaluation | `EvalCase`, `JudgeVerdict` | YAML validated at load time, judge with Structured Outputs |

The LangGraph state is a `TypedDict` with reducers, which is idiomatic and avoids revalidating on every node
merge. The Pydantic objects travel *inside* it.

### 7. Graph design and what runs in parallel
- **After `load_history`, the classifier and the policy prefetch run concurrently.** `load_history` is a few
  milliseconds of SQL, and the classifier needs the previous reply to read follow-ups like
  "pedido 5, email x" correctly.
  - When the intent is about policy and the retrieved chunk is similar enough, the excerpts go into the context
    and the agent answers **in a single model call, with no tool round**. The return question in the examples
    took 1 agent call.
  - Otherwise they are discarded.
- **Tools run in parallel:** the model issues several tool calls at once (`parallel_tool_calls`), and they run
  concurrently.
- **Fixed prompt first:** the system prompt and the tool schemas go first and never change; the dynamic context
  goes last. That makes OpenAI's prompt cache effective.
- **Blocked and off-topic messages never reach the agent:** they get a canned reply in about 0.3 s.
- **Streaming:** the UI receives classification, status and tool events live over SSE. The *reply* is released
  only after validation, which is why there is no token streaming (a trade-off for correctness).

### 8. Guardrails: heuristics and a classifier on the way in, deterministic checks on the way out
- **Input:**
  - Zero-cost heuristics: Unicode NFKC folding (it defeats lookalike letters), known injection patterns and
    base64 payloads.
  - The classifier contract.
  - One **provider-agnostic decision function**:
    - block on a strong heuristic or a high-confidence attack;
    - proceed with a *heightened caution* note when unsure;
    - give a canned reply for clear off-topic messages.
  - Customer text and tool results are passed as *data*, never as instructions.
- **Output — every reply is checked by code before the customer sees it:**
  - **Grounding:** every `R$`, `%`, `Nx` and `N dias` must appear in this turn's tool results, in the injected
    policy excerpts or in the conversation. An invented price is rejected.
  - **Prompt leakage:** a canary token, and long verbatim runs of the instructions that are not also public text.
  - **Personal data:** an e-mail or phone may appear only if it belongs to the verified customer or to the store.
  - A failed check gets one corrective retry. A second failure gets a safe fallback with a handoff to the team.
- **Measured (see [Evaluation](#evaluation)):** an extra LLM review of each reply cost about 2 s per turn and
  caught nothing in 56 evaluated turns that the code checks had not already handled. So it is **opt-in**
  (`OUTPUT_REVIEW=true`), and the deterministic checks always run.

### 9. Prompt strategy
- **Static block:**
  - the persona (tone from manual §7.1, service flow from §7.2);
  - the *non-negotiable rules* (no figure without a tool, promotion shown as original price + promotional price
    + %, LGPD, instruments only, no invented discounts);
  - a short "when to use each tool" guide and the reply format.
- **Dynamic block:** the current date and time from the business clock, whether the store is open (and when the
  human team returns), the classifier's reading, the caution flag and the prefetched policy excerpts.
- No few-shot examples: the evaluation did not need them.
- The prompt is versioned in [`prompts/system.md`](backend/src/emporio/assistant/prompts/system.md).

### 10. Conversation persistence
- The `conversations`, `messages` and `support_tickets` tables live in the app's own schema (Alembic).
- Each assistant message stores an **audit payload**: classifier reading, route, tool calls with arguments and
  latency, citations, rejected drafts and token usage. That supports multi-turn context ("e em 10x?"), a human
  taking over a conversation, and debugging.
- I did not use the LangGraph checkpointer: it creates tables outside the migrations, and the history is a
  domain concept here.

### 11. DDD and SOLID — and where I kept it light
- **What follows the rules:**
  - Ports are small `Protocol`s (`ProductReader`, `OrderReader`, `PolicyRetriever`, `InputClassifier`,
    `ChatModel`, `Clock`). The agent graph only knows the `ChatModel` port: the OpenAI Responses adapter
    ([`openai_chat.py`](backend/src/emporio/assistant/openai_chat.py)) is the single place that knows the SDK and
    its message format.
  - The agent node only orchestrates: the prompt context is a pure function
    ([`context.py`](backend/src/emporio/assistant/context.py)) and the output checks live in an `OutputValidator`.
  - Business rules live in the domain, including the store's scope (accessories and category synonyms). The
    texts shown to the model are derived from the domain constants (thresholds, opening hours), never retyped.
  - New providers are new adapters (OpenAI and Jev share one contract and one suite of contract tests).
  - The composition root is the only place that knows the concrete classes.
- **Where I chose not to add ceremony:**
  - one ORM module for the whole small schema;
  - no dependency-injection framework;
  - use cases are grouped in one service class per context (`CatalogService`, `OrderService`, `StoreService`),
    where each public method is one intention, instead of one class per use case;
  - the PT-BR labels and explanations the customer reads sit next to the domain enums and rules that produce
    them, instead of in a separate translation layer.

### 12. Running: Docker Compose, not Kubernetes
- **Why:** one command for the evaluator, and the same `compose.yaml` runs locally and on the server (where a
  small override joins the edge to the existing tunnel's network).
- **Security settings, the same as the other apps on my server:**
  - pinned image digests;
  - `no-new-privileges` and `cap_drop: ALL`;
  - memory, CPU and process limits;
  - non-root user and log rotation.
- **Trade-off:** Kubernetes would only add operational surface at this scale.

---

## Data handling and assumptions

Every CSV row is validated with Pydantic before ingestion. The full report, with each finding and how it is
handled, is in [`reports/data-quality.md`](reports/data-quality.md). The main points:

| Finding | Treatment |
|---|---|
| Product 96 is `active` with zero stock; 113/136 are discontinued; 130 is "coming soon" | Availability comes from status *and* stock; non-sellable items are never offered, and similar in-stock items are suggested |
| Several promotions for the same product, all without validity dates | Only `is_active` counts; the best active one wins |
| Order totals 3 and 20 differ from the current item prices; orders 3 and 14 contain the "coming soon" product | Totals are historical and shown as stored; documented as inconsistencies |
| Orders have no receipt date | For delivered orders, the estimated delivery date is taken as the receipt date (return windows count from receipt) |
| The data ends in 03/2026 | An injectable business clock (`APP_REFERENCE_DATE`) makes return scenarios demonstrable |
| The manual gives the e-mail with and without an accent, and two WhatsApp numbers | The unaccented e-mail is used; both numbers are shown as the manual states them |
| "Up to 3x: no minimum (except below R$ 50,00)" is ambiguous | Read as a R$ 50,00 minimum installment for 2x–3x |
| The manual does not define the "metropolitan region" or list holidays | The city of Campo Grande is treated as the metro region; Brazil's fixed national holidays are used (movable ones are a known limitation) |
| Regret returns apply to online purchases, but orders have no channel | All orders are assumed to be online |
| Near-duplicate customer names (e.g. "Bruno Carvalho Martins" and "Bruno Carvalho") | Identity is checked by e-mail or phone, never by name |

---

## Evaluation

`make eval` runs [28 golden-set cases](backend/src/emporio/evaluation/golden_set.yaml) against the real models,
with the business date pinned to 2026-01-22. They cover catalog, prices, installments, promotions, stock,
discontinued products, returns with and without verification, LGPD, shipping, hours, warranty, accessories,
off-topic messages, three manipulation attempts and handoff.

Each case checks:
- the outcome;
- the **tools the agent chose**;
- facts that must and must not appear;
- an LLM-as-judge verdict (Structured Outputs) on language, tone and persona.

| Classifier | Passed | Security / scope / LGPD | Turn latency p50 / p95 | Classifier p50 / p95 | Agent calls / turn | Tone (1–5) |
|---|---|---|---|---|---|---|
| OpenAI `gpt-6-luna` (default) | **28/28** | 7/7 | 6.5 s / 9.2 s | 1.6 s / 2.8 s | 1.64 | 4.62 |
| Jev (optional) | **28/28** | 7/7 | 5.0 s / 7.5 s | 0.18 s / 0.26 s | 1.71 | 4.52 |

The agent is generative, so results vary a little between runs. In one run of the Jev configuration, two policy
cases (the 7-day regret window and the 90-day warranty) answered correctly but without the exact expected fact.
They passed 5/5 each on a targeted rerun, and the full rerun above passed 28/28. In no run did an attack, a made-up
figure or another customer's data get through.

What the evaluation changed:
- **The LLM output review became opt-in.** In the run that measured it, the default path's p50 was 8.1 s with the
  review on and 6.7 s with it off,
  with no loss in results.
- **A security case was rewritten.** Blocking a role-play discount request and safely refusing it are both
  correct, so the case now accepts either.
- **The prompt-leak detector was recalibrated.** It had flagged "o número do pedido e o e-mail" (normal service
  language), so phrases that also appear in public text no longer count.

The full per-case table is in [`reports/eval-report.md`](reports/eval-report.md). The automated tests (157:
domain rules, ingestion, chunking, retrieval, every tool, classifier contract, graph routing and parallelism,
API) run in CI without paid API calls.

## Case study: a pluggable classifier (OpenAI vs. Jev)

[Jev](https://docs.typesafe.ai) (TypeSafe AI, released in September 2026) is a decision-only "System One" model.
It does not generate text: it answers typed questions (choice, score, yes/no) with probabilities. That makes it
a natural fit for the classifier port.

- **Same contract, same definitions:** the labels are defined once
  ([`labels.py`](backend/src/emporio/assistant/classification/labels.py)), and that module generates both the
  OpenAI prompt and the Jev questions.
- **Same decisions:** Jev's probabilities are bucketed into the same confidence levels, so one decision function
  routes both. The contract tests require identical routes. In a live check of 8 Portuguese messages, both
  providers routed identically.
- **Never a single point of failure:** any Jev error or timeout falls back to OpenAI. Without a
  `TYPESAFE_API_KEY`, nothing changes for the user.
- **Result:**
  - Same accuracy on the golden set (28/28 each).
  - Classification is **~8x faster** (≈190 ms vs 1.6 s p50). Because the classifier sits on the critical path,
    that took 0.9–1.7 s off the median turn across the evaluation runs.
  - The OpenAI classifier blocked the role-play attempt outright; Jev let it through with a caution flag, and
    the agent refused.
- **Conclusion:** a dedicated decision model is a real latency win for the guard layer. Keeping it behind a port
  with a fallback is what makes it safe to adopt.

## Example conversations

Generated by replaying [`examples/scripts.yaml`](examples/scripts.yaml) against the real agent (`make examples`).
Each one includes a collapsible "backstage" section with the classifier reading, the tool calls and the
citations:

1. [Catalog: guitars up to R$ 1,000, then installments](examples/conversations/01-catalog-guitars-up-to-1000.md)
2. [Takamine GD20 price, PIX and the promotion rule](examples/conversations/02-price-takamine-gd20-and-payment.md)
3. [**Return after regret** — LGPD verification, the return window computed by code, a ticket opened](examples/conversations/03-return-after-regret.md) *(non-trivial)*
4. [Address, hours, accessories, off-topic and shipping](examples/conversations/04-store-info-accessories-and-out-of-scope.md)
5. [Prompt-injection attempts](examples/conversations/05-prompt-injection-attempts.md)

## Known limitations and what I would do with more time

- **Shipping prices for other cities** need a carrier API (Correios/Jadlog). Today the agent explains the rule and
  asks for the ZIP code instead of inventing a price.
- **Customer authentication** is "order number + e-mail/phone". A real channel would use an OTP or the WhatsApp
  identity.
- **Promotions have no validity dates** in the data; `is_active` is trusted. **Movable holidays** (Carnival, Good
  Friday) are not in the calendar.
- **No token streaming:** replies are released after validation. Incremental validation per sentence would allow it.
- **The rate limiter is in-memory** (fine for one replica). Several replicas would need Redis.
- **Production observability:** structured traces per turn (OpenTelemetry or LangSmith), cost dashboards, and
  alerts on fallback and rejection rates. The audit payload already records the raw data.
- **Evaluation:** a larger golden set built from real (anonymised) conversations, multi-turn judged scenarios,
  and calibration of the classifier thresholds on real traffic.
- **Real channels:** a WhatsApp Business adapter. The API is already channel-agnostic (`conversations.channel`).
- **Human handoff:** tickets are stored but go nowhere yet. A helpdesk integration would close the loop.

## AI-assisted development

I built this with **Claude Code** (Anthropic's CLI agent), working as the architect and reviewer while the
assistant wrote most of the code. My workflow:

1. **Planning first, in a local document I iterated on.** The assistant analysed the brief, the manual and the
   CSVs and drafted a plan. I reviewed it over several rounds and made the calls:
   - one agent instead of a supervisor;
   - OpenAI as the provider;
   - Jev only as an optional case study that must behave identically;
   - Compose instead of Kubernetes;
   - deployment on my own server, reusing its existing tunnel.
2. **Project conventions as context:** a [`CLAUDE.md`](CLAUDE.md) with the architecture rules (dependency
   direction, Pydantic only at the boundaries, money as `Decimal`, no business rule in prompts) and **project
   skills** in [`.claude/skills/`](.claude/skills/) with recipes for recurring changes (new tool, new classifier
   field, migration, eval). Every change followed the same definition of done.
3. **Phase by phase, one commit per phase**, each checked with tests and lint before moving on (strict mypy, and
   CI on every push).
4. **Verification against reality, not just tests:**
   - Spikes against the real APIs before building on assumptions (model IDs, strict tools combined with
     Structured Outputs, the Jev REST API).
   - End-to-end runs in the terminal and a headless browser.
   - The evaluation drove changes: the leak detector was recalibrated and the LLM review became opt-in.
   - Data analysis found inconsistencies I then documented.
5. **What the tests caught along the way:** a real rounding bug in the installment rule (R$ 149,99 in 3x was being
   accepted). The tests also showed that two of the expected values I had written were wrong, while the
   implementation was right. CI caught a formatting slip.

The assistant was fast at scaffolding, recall of library APIs, and consistent refactors across layers. I kept
control of the decisions, the scope and the reviews.

## Repository map and commands

```
backend/src/emporio/
├── shared/            Money, Clock, domain errors
├── catalog/ orders/ store/ knowledge/ conversation/   bounded contexts (domain / application / infrastructure)
├── assistant/         LangGraph graph, tools (Args/Views + handlers), classification, guardrails, prompts
├── ingestion/         Pydantic row models, loader, data-quality analysis, idempotent pipeline
├── evaluation/        golden set, runner, example generator
├── api/               FastAPI app, routes, SSE schemas, rate limits
├── container.py       composition root
└── cli.py             emporio ingest | chat | ask | eval | examples | data-report
backend/migrations/    Alembic (pgvector HNSW, pg_trgm, generated Portuguese tsvector)
backend/tests/         unit · graph (scripted fakes) · integration (real Postgres)
frontend/              Vue 3 + Vite + TypeScript chat, Caddy edge config
data/raw/              original challenge data (CSVs + policy manual)
examples/ reports/     example conversations, evaluation and data-quality reports
deploy/homeserver/     server override, audit and runbook · scripts/: deploy, smoke test, backup
```
