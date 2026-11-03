"""Return and exchange eligibility (store manual §4 and §8).

- Regret (online purchase): up to 7 calendar days after receipt, unused, original packaging.
- Manufacturing defect: exchange within 30 calendar days after the purchase; afterwards the manufacturer
  warranty applies (the store can intermediate). Legal warranty: 90 days after receipt (§8.1).
- Preference (colour, model, size): up to 7 days, subject to stock.
- Never eligible: customised items / special setup, "final sale" clearance items, wind-instrument
  mouthpieces (hygiene). The data has no flag for these, so they are returned as conditions to confirm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from emporio.orders.domain.models import Order, OrderStatus

REGRET_WINDOW_DAYS = 7
DEFECT_EXCHANGE_WINDOW_DAYS = 30
PREFERENCE_WINDOW_DAYS = 7
LEGAL_WARRANTY_DAYS = 90

GENERAL_EXCLUSIONS = (
    "instrumentos com personalização ou ajustes sob encomenda (setup, regulagem especial)",
    'produtos de liquidação com aviso explícito de "venda final"',
    "boquilhas de instrumentos de sopro (por higiene)",
)


class ReturnReason(StrEnum):
    REGRET = "regret"
    DEFECT = "defect"
    PREFERENCE = "preference"


class ReturnOutcome(StrEnum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    MANUFACTURER_WARRANTY = "manufacturer_warranty"
    NOT_YET_RECEIVED = "not_yet_received"


@dataclass(frozen=True)
class ReturnDecision:
    outcome: ReturnOutcome
    reason: ReturnReason
    policy_section: str
    explanation: str
    window_start: date | None = None
    deadline: date | None = None
    days_elapsed: int | None = None
    conditions: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = field(default=GENERAL_EXCLUSIONS)

    @property
    def eligible(self) -> bool:
        return self.outcome is ReturnOutcome.ELIGIBLE


def evaluate_return(order: Order, reason: ReturnReason, today: date) -> ReturnDecision:
    if order.status is OrderStatus.CANCELLED:
        return ReturnDecision(
            outcome=ReturnOutcome.NOT_ELIGIBLE,
            reason=reason,
            policy_section="4. Política de Trocas e Devoluções",
            explanation="Este pedido foi cancelado, então não há produto a devolver ou trocar.",
        )

    received = order.received_on
    if received is None:
        return ReturnDecision(
            outcome=ReturnOutcome.NOT_YET_RECEIVED,
            reason=reason,
            policy_section="4. Política de Trocas e Devoluções",
            explanation=(
                "O pedido ainda não foi entregue. Os prazos de devolução e troca começam a contar "
                "a partir do recebimento do produto."
            ),
            next_steps=(
                "Se quiser desistir antes da entrega, a equipe de atendimento verifica a "
                "possibilidade de cancelamento.",
            ),
        )

    if reason is ReturnReason.REGRET:
        return _window_decision(
            reason=reason,
            start=received,
            window_days=REGRET_WINDOW_DAYS,
            today=today,
            section="4.1 Direito de Arrependimento (Compras Online)",
            conditions=(
                "produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais",
            ),
            next_steps=(
                "Reembolso na mesma forma de pagamento original em até 10 dias úteis.",
                "O frete de devolução por arrependimento é por conta da loja.",
            ),
            label="a devolução por arrependimento",
            counted_from="o recebimento",
        )

    if reason is ReturnReason.PREFERENCE:
        return _window_decision(
            reason=reason,
            start=received,
            window_days=PREFERENCE_WINDOW_DAYS,
            today=today,
            section="4.3 Trocas por Preferência",
            conditions=(
                "produto em perfeito estado e na embalagem original",
                "sujeito à disponibilidade do produto desejado em estoque",
            ),
            next_steps=("Diferenças de valor são cobradas ou reembolsadas conforme o caso.",),
            label="a troca por preferência",
            counted_from="o recebimento",
        )

    # Defect: 30 days from the purchase for a store exchange, then manufacturer warranty.
    decision = _window_decision(
        reason=reason,
        start=order.order_date,
        window_days=DEFECT_EXCHANGE_WINDOW_DAYS,
        today=today,
        section="4.2 Trocas por Defeito",
        conditions=(
            "defeito de fabricação (danos por mau uso, quedas, umidade excessiva ou modificações "
            "não autorizadas não são cobertos)",
        ),
        next_steps=("A equipe avalia o produto e faz a troca.",),
        label="a troca por defeito direto na loja",
        counted_from="a compra",
    )
    if decision.eligible:
        return decision
    legal_deadline = received + timedelta(days=LEGAL_WARRANTY_DAYS)
    return ReturnDecision(
        outcome=ReturnOutcome.MANUFACTURER_WARRANTY,
        reason=reason,
        policy_section="4.2 Trocas por Defeito / 8. Garantia",
        explanation=(
            f"O prazo de {DEFECT_EXCHANGE_WINDOW_DAYS} dias para troca direta na loja já passou. "
            "Agora o caminho é a garantia do fabricante, e a Empório pode intermediar o processo."
        ),
        window_start=order.order_date,
        deadline=decision.deadline,
        days_elapsed=decision.days_elapsed,
        conditions=decision.conditions,
        next_steps=(
            "Acionar a garantia do fabricante (normalmente de 6 meses a 2 anos, conforme o "
            "certificado que acompanha o produto); a loja pode intermediar.",
            f"A garantia legal de {LEGAL_WARRANTY_DAYS} dias contra defeitos de fabricação vai até "
            f"{legal_deadline:%d/%m/%Y}.",
        ),
    )


def _window_decision(
    *,
    reason: ReturnReason,
    start: date,
    window_days: int,
    today: date,
    section: str,
    conditions: tuple[str, ...],
    next_steps: tuple[str, ...],
    label: str,
    counted_from: str,
) -> ReturnDecision:
    deadline = start + timedelta(days=window_days)
    elapsed = (today - start).days
    if today <= deadline:
        return ReturnDecision(
            outcome=ReturnOutcome.ELIGIBLE,
            reason=reason,
            policy_section=section,
            explanation=(
                f"Ainda está dentro do prazo de {window_days} dias corridos para {label}, "
                f"contados a partir de {counted_from} ({start:%d/%m/%Y}). "
                f"O prazo vai até {deadline:%d/%m/%Y}."
            ),
            window_start=start,
            deadline=deadline,
            days_elapsed=elapsed,
            conditions=conditions,
            next_steps=next_steps,
        )
    return ReturnDecision(
        outcome=ReturnOutcome.NOT_ELIGIBLE,
        reason=reason,
        policy_section=section,
        explanation=(
            f"O prazo de {window_days} dias corridos para {label}, contados a partir de "
            f"{counted_from} ({start:%d/%m/%Y}), terminou em {deadline:%d/%m/%Y}."
        ),
        window_start=start,
        deadline=deadline,
        days_elapsed=elapsed,
        conditions=conditions,
    )
