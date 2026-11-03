from emporio.evaluation.runner import EvalCase, check, load_cases


def events(
    reply: str, outcome: str = "answered", tools: tuple[str, ...] = (), route: str = "proceed"
) -> list[dict]:  # type: ignore[type-arg]
    return [
        {"type": "classification", "route": route, "latency_ms": 10, "assessment": {}},
        *({"type": "tool", "name": t} for t in tools),
        {"type": "message", "outcome": outcome, "reply": {"message": reply}},
        {"type": "done", "latency_ms": 100, "model_rounds": 1},
    ]


def test_golden_set_is_valid() -> None:
    cases = load_cases()
    assert len(cases) >= 25
    assert len({c.id for c in cases}) == len(cases)


def test_checks_tools_text_and_outcome() -> None:
    case = EvalCase(
        id="x",
        category="data",
        turns=["?"],
        expected_tools=["get_product|search_products"],
        must_contain=["2.199,00"],
        must_not_contain=["GF-3D"],
    )

    assert check(case, events("Custa R$ 2.199,00", tools=("search_products",)))[0] == []
    failures, _ = check(case, events("Custa R$ 2.000,00 e o GF-3D também"))
    assert failures == [
        "missing tool get_product|search_products",
        "missing text '2.199,00'",
        "forbidden text 'GF-3D'",
    ]


def test_expected_outcome() -> None:
    case = EvalCase(id="x", category="security", turns=["?"], expected_outcome=["blocked"])

    assert check(case, events("não posso", outcome="blocked", route="block"))[0] == []
    assert check(case, events("claro!"))[0] == ["outcome answered not in blocked"]
