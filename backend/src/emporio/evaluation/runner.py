"""Golden-set evaluation against the real models. Writes JSON results and a Markdown report."""

from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from emporio.config import Settings
from emporio.container import Container

GOLDEN_SET = Path(__file__).with_name("golden_set.yaml")
EVAL_REFERENCE_DATE = date(2026, 1, 22)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    turns: list[str] = Field(min_length=1)
    expected_tools: list[str] = []
    expected_outcome: list[Literal["answered", "blocked", "off_topic", "fallback"]] = []
    """Acceptable outcomes; empty means the agent must answer."""
    expected_route: Literal["proceed", "block", "off_topic"] | None = None
    must_contain: list[str] = []
    must_not_contain: list[str] = []


class JudgeVerdict(BaseModel):
    """LLM-as-judge for what code cannot check: tone and persona (manual §7.1)."""

    model_config = ConfigDict(extra="forbid")

    portuguese_br: bool
    friendly_professional_tone: bool
    stays_in_store_persona: bool
    score: int = Field(ge=1, le=5, description="Overall service quality, 5 = excellent")
    note: str = Field(description="One short sentence.")


JUDGE_INSTRUCTIONS = """You review one reply from Lia, the virtual assistant of Empório da Música (a Brazilian
musical-instrument store). Expected tone: informal but professional, welcoming, like a friend who knows
music; short WhatsApp-style messages; Brazilian Portuguese. Judge only tone, language and persona — not facts."""


@dataclass
class CaseResult:
    id: str
    category: str
    passed: bool
    failures: list[str]
    outcome: str | None
    route: str | None
    tools: list[str]
    reply: str
    latency_ms: int
    classifier_ms: int | None
    model_rounds: int
    input_tokens: int
    output_tokens: int
    judge: dict[str, Any] | None = field(default=None)
    rejections: list[str] = field(default_factory=list)


def load_cases(path: Path = GOLDEN_SET) -> list[EvalCase]:
    return [
        EvalCase.model_validate(raw) for raw in yaml.safe_load(path.read_text(encoding="utf-8"))
    ]


def _contains(text: str, alternatives: str) -> bool:
    lowered = text.lower()
    return any(option.lower() in lowered for option in alternatives.split("|"))


def check(case: EvalCase, events: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    message = next((e for e in events if e["type"] == "message"), None)
    classification = next((e for e in events if e["type"] == "classification"), None)
    tools = [e["name"] for e in events if e["type"] == "tool"]
    reply = message["reply"]["message"] if message else ""
    outcome = message["outcome"] if message else None
    route = classification["route"] if classification else None
    failures: list[str] = []
    acceptable = case.expected_outcome or ["answered"]
    if outcome not in acceptable:
        failures.append(f"outcome {outcome} not in {'/'.join(acceptable)}")
    if case.expected_route and route != case.expected_route:
        failures.append(f"route {route} != {case.expected_route}")
    for expected in case.expected_tools:
        if not any(tool in tools for tool in expected.split("|")):
            failures.append(f"missing tool {expected}")
    failures += [f"missing text '{t}'" for t in case.must_contain if not _contains(reply, t)]
    failures += [f"forbidden text '{t}'" for t in case.must_not_contain if _contains(reply, t)]
    return failures, {
        "reply": reply,
        "outcome": outcome,
        "route": route,
        "tools": tools,
        "classification": classification,
    }


async def _judge(client: AsyncOpenAI, model: str, question: str, reply: str) -> JudgeVerdict | None:
    response = await client.responses.parse(
        model=model,
        instructions=JUDGE_INSTRUCTIONS,
        input=json.dumps({"customer": question, "reply": reply}, ensure_ascii=False),
        text_format=JudgeVerdict,
        reasoning={"effort": "none"},
    )
    return response.output_parsed


async def run_case(container: Container, case: EvalCase) -> CaseResult:
    conversation_id = await container.conversations.create("eval")
    events: list[dict[str, Any]] = []
    for turn in case.turns:
        events = [event async for event in container.assistant.stream(conversation_id, turn)]
    failures, seen = check(case, events)
    done = next(e for e in events if e["type"] == "done")
    usage = await container.conversations.history(conversation_id, limit=1)
    tokens = usage[-1].payload.get("usage", []) if usage else []
    rejections = usage[-1].payload.get("rejections", []) if usage else []
    judge = None
    if seen["outcome"] == "answered":
        verdict = await _judge(
            container.openai, container.settings.classifier_model, case.turns[-1], seen["reply"]
        )
        if verdict:
            judge = verdict.model_dump()
            if not (verdict.portuguese_br and verdict.stays_in_store_persona):
                failures.append(f"judge: {verdict.note}")
    classification = seen["classification"]
    return CaseResult(
        id=case.id,
        category=case.category,
        passed=not failures,
        failures=failures,
        outcome=seen["outcome"],
        route=seen["route"],
        tools=seen["tools"],
        reply=seen["reply"],
        latency_ms=done["latency_ms"],
        classifier_ms=classification["latency_ms"] if classification else None,
        model_rounds=done["model_rounds"],
        input_tokens=sum(u.get("input", 0) for u in tokens),
        output_tokens=sum(u.get("output", 0) for u in tokens),
        judge=judge,
        rejections=rejections,
    )


async def run_eval(settings: Settings, output_dir: Path, concurrency: int = 4) -> Path:
    settings = settings.model_copy(update={"app_reference_date": EVAL_REFERENCE_DATE})
    container = Container.build(settings)
    provider = "jev" if settings.jev_enabled else "openai"
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(case: EvalCase) -> CaseResult:
        async with semaphore:
            return await run_case(container, case)

    try:
        results = await asyncio.gather(*(guarded(case) for case in load_cases()))
    finally:
        await container.close()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"eval-{provider}.json").write_text(
        json.dumps(
            {
                "provider": provider,
                "agent_model": settings.agent_model,
                "results": [asdict(r) for r in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report = output_dir / "eval-report.md"
    report.write_text(render_report(output_dir), encoding="utf-8")
    return report


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [r["latency_ms"] for r in results]
    classifier = [r["classifier_ms"] for r in results if r["classifier_ms"] is not None]
    judged = [r["judge"]["score"] for r in results if r.get("judge")]
    security = [r for r in results if r["category"] in ("security", "scope", "lgpd")]
    return {
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "security_passed": sum(r["passed"] for r in security),
        "security_total": len(security),
        "p50": _percentile(latencies, 0.5),
        "p95": _percentile(latencies, 0.95),
        "classifier_p50": _percentile(classifier, 0.5),
        "classifier_p95": _percentile(classifier, 0.95),
        "rounds": statistics.mean(r["model_rounds"] for r in results),
        "judge": statistics.mean(judged) if judged else 0,
        "tokens": statistics.mean(r["input_tokens"] + r["output_tokens"] for r in results),
        "rejected_deterministic": sum(
            1 for r in results for p in r.get("rejections", []) if not p.startswith("revisão")
        ),
        "rejected_review": sum(
            1 for r in results for p in r.get("rejections", []) if p.startswith("revisão")
        ),
    }


def render_report(output_dir: Path) -> str:
    runs = {}
    for provider in ("openai", "jev"):
        path = output_dir / f"eval-{provider}.json"
        if path.exists():
            runs[provider] = json.loads(path.read_text(encoding="utf-8"))
    lines = [
        "# Evaluation report",
        "",
        f"Golden set: {len(load_cases())} cases (`backend/src/emporio/evaluation/golden_set.yaml`), real models, "
        f"business clock pinned to {EVAL_REFERENCE_DATE:%Y-%m-%d}. Each case checks the final outcome, the tools "
        "the agent chose, facts that must / must not appear, and an LLM-as-judge verdict on tone and persona.",
        "",
        "## Summary",
        "",
        "| Classifier | Passed | Security/scope/LGPD | Turn latency p50 / p95 | Classifier p50 / p95 | Agent calls / turn | Tone score (1-5) | Tokens / turn | Replies rejected (code / LLM review) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for provider, run in runs.items():
        s = _summary(run["results"])
        lines.append(
            f"| {provider} | {s['passed']}/{s['total']} | {s['security_passed']}/{s['security_total']} | "
            f"{s['p50'] / 1000:.1f} s / {s['p95'] / 1000:.1f} s | {s['classifier_p50']} ms / {s['classifier_p95']} ms | "
            f"{s['rounds']:.2f} | {s['judge']:.2f} | {s['tokens']:.0f} | "
            f"{s['rejected_deterministic']} / {s['rejected_review']} |"
        )
    for provider, run in runs.items():
        lines += [
            "",
            f"## Cases — classifier `{provider}` (agent `{run['agent_model']}`)",
            "",
            "| Case | Category | Result | Tools | Latency | Notes |",
            "|---|---|---|---|---|---|",
        ]
        for r in run["results"]:
            note = (
                "; ".join(r["failures"])
                if r["failures"]
                else (r["judge"]["note"] if r.get("judge") else r["outcome"])
            )
            lines.append(
                f"| `{r['id']}` | {r['category']} | {'✅' if r['passed'] else '❌'} | {', '.join(r['tools']) or '—'} | "
                f"{r['latency_ms'] / 1000:.1f} s | {note.replace('|', '/')} |"
            )
    return "\n".join(lines) + "\n"
