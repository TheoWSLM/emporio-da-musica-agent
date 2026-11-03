from datetime import datetime
from zoneinfo import ZoneInfo

from emporio.assistant.classification.assessment import InputAssessment
from emporio.assistant.context import STATIC_FACTS, turn_context
from emporio.assistant.guardrails.output_validator import OutputValidator
from emporio.knowledge.domain.models import PolicyHit
from emporio.store.domain.hours import store_status
from tests.graph.fakes import FakeOutputClassifier, assessment

TZ = ZoneInfo("America/Campo_Grande")
POLICY = PolicyHit(
    "4. Trocas > 4.1 Arrependimento", "4.1 Arrependimento", "até 7 (sete) dias", 0.1, 0.8
)


def context(
    moment: datetime,
    a: InputAssessment,
    caution: bool = False,
    policies: list[PolicyHit] | None = None,
) -> str:
    return turn_context(
        now=moment,
        store=store_status(moment),
        assessment=a,
        heightened_caution=caution,
        policies=policies or [],
    )


def test_context_when_open_with_policies() -> None:
    text = context(
        datetime(2026, 11, 4, 10, 0, tzinfo=TZ),
        assessment(intent="return_exchange"),
        policies=[POLICY],
    )

    assert "Loja aberta agora." in text and "[4. Trocas > 4.1 Arrependimento]" in text
    assert "ATENÇÃO" not in text


def test_context_when_closed_with_caution_and_frustration() -> None:
    text = context(
        datetime(2026, 11, 8, 10, 0, tzinfo=TZ), assessment(frustration="angry"), caution=True
    )

    assert (
        "Loja fechada agora (domingo). O atendimento humano retorna segunda, 09/11 às 09:00."
        in text
    )
    assert "ATENÇÃO" in text and "frustrado" in text


def test_static_facts_carry_the_quotable_store_data() -> None:
    assert (
        "Rua 14 de Maio" in STATIC_FACTS
        and "24 horas úteis" in STATIC_FACTS
        and "5% PIX" in STATIC_FACTS
    )


def validator(review: bool = False, **flags: bool) -> OutputValidator:
    return OutputValidator(
        system_prompt="instrucoes",
        canary="CANARY",
        reviewer=FakeOutputClassifier(**flags),
        review_enabled=review,
    )


async def test_validator_accepts_grounded_replies() -> None:
    problems = await validator().problems(
        reply="Custa R$ 2.199,00.",
        customer_message="preço?",
        sources=['{"price":"R$ 2.199,00"}'],
        allowed_contacts=[],
    )
    assert problems == []


async def test_validator_reports_every_kind_of_problem() -> None:
    problems = await validator(review=True, off_persona=True).problems(
        reply="Custa R$ 9,00. CANARY. Fale com lucas@x.com",
        customer_message="?",
        sources=[],
        allowed_contacts=[],
    )
    kinds = {p.split(":")[0] for p in problems}
    assert kinds == {
        "valor sem fonte nas ferramentas",
        "vazamento",
        "dado pessoal não verificado",
        "revisão",
    }


async def test_review_is_skipped_when_disabled() -> None:
    problems = await validator(review=False, off_persona=True).problems(
        reply="Olá!", customer_message="oi", sources=[], allowed_contacts=[]
    )
    assert problems == []
