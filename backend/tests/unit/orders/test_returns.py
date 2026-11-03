from datetime import date

from emporio.orders.domain.models import Order, OrderStatus, PaymentMethod
from emporio.orders.domain.returns import ReturnOutcome, ReturnReason, evaluate_return
from emporio.shared.money import Money


def order(status: OrderStatus = OrderStatus.DELIVERED) -> Order:
    return Order(
        id=5,
        customer_id=5,
        order_date=date(2026, 1, 5),
        status=status,
        total=Money.of(4599),
        payment=PaymentMethod.parse("pix"),
        estimated_delivery=date(2026, 1, 18),
    )


def test_regret_on_the_seventh_day_is_still_allowed() -> None:
    decision = evaluate_return(order(), ReturnReason.REGRET, date(2026, 1, 25))

    assert decision.outcome is ReturnOutcome.ELIGIBLE
    assert decision.deadline == date(2026, 1, 25)


def test_regret_on_the_eighth_day_is_refused() -> None:
    decision = evaluate_return(order(), ReturnReason.REGRET, date(2026, 1, 26))

    assert decision.outcome is ReturnOutcome.NOT_ELIGIBLE
    assert "25/01/2026" in decision.explanation


def test_defect_within_thirty_days_of_purchase_is_exchanged_by_the_store() -> None:
    decision = evaluate_return(order(), ReturnReason.DEFECT, date(2026, 2, 4))

    assert decision.outcome is ReturnOutcome.ELIGIBLE


def test_defect_after_thirty_days_goes_to_manufacturer_warranty() -> None:
    decision = evaluate_return(order(), ReturnReason.DEFECT, date(2026, 2, 5))

    assert decision.outcome is ReturnOutcome.MANUFACTURER_WARRANTY
    assert any("18/04/2026" in step for step in decision.next_steps)  # 90-day legal warranty


def test_preference_window_counts_from_receipt() -> None:
    assert evaluate_return(order(), ReturnReason.PREFERENCE, date(2026, 1, 25)).eligible
    assert not evaluate_return(order(), ReturnReason.PREFERENCE, date(2026, 1, 26)).eligible


def test_orders_not_yet_received_have_no_window_yet() -> None:
    decision = evaluate_return(order(OrderStatus.SHIPPED), ReturnReason.REGRET, date(2026, 1, 20))

    assert decision.outcome is ReturnOutcome.NOT_YET_RECEIVED


def test_cancelled_orders_are_not_eligible() -> None:
    decision = evaluate_return(order(OrderStatus.CANCELLED), ReturnReason.REGRET, date(2026, 1, 20))

    assert decision.outcome is ReturnOutcome.NOT_ELIGIBLE


def test_exclusions_are_always_reported() -> None:
    decision = evaluate_return(order(), ReturnReason.REGRET, date(2026, 1, 20))

    assert any("boquilhas" in item for item in decision.exclusions)
