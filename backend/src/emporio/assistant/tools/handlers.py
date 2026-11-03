"""Tool handlers: validate args, call one use case, map the result to a view. No business rules here."""

from __future__ import annotations

from decimal import Decimal

from emporio.assistant.tools.context import ToolContext
from emporio.assistant.tools.schemas import (
    ErrorView,
    GetProductArgs,
    InstallmentView,
    OpenTicketArgs,
    OrderItemView,
    OrderLookupArgs,
    OrderStatusView,
    PaymentOptionsArgs,
    PaymentOptionsView,
    PolicyHitView,
    ProductDetailsView,
    ProductView,
    PromotionView,
    ReturnEligibilityArgs,
    ReturnEligibilityView,
    SearchPoliciesArgs,
    SearchPoliciesView,
    SearchProductsArgs,
    SearchProductsView,
    ShippingArgs,
    ShippingOptionView,
    ShippingView,
    StoreStatusArgs,
    StoreStatusView,
    TicketView,
    View,
)
from emporio.catalog.application.use_cases import ProductOffer, SearchCriteria
from emporio.catalog.domain.installments import max_installments
from emporio.catalog.domain.models import Promotion
from emporio.catalog.domain.pricing import PIX_DISCOUNT_PERCENT
from emporio.conversation.domain.models import RESPONSE_SLA, TicketType
from emporio.ingestion.enrichment import readable_specs
from emporio.orders.application.use_cases import OrderLookup, Verification
from emporio.orders.domain.models import OrderStatus
from emporio.orders.domain.returns import ReturnOutcome, ReturnReason
from emporio.shared.errors import NotFoundError
from emporio.shared.money import Money
from emporio.store.domain.hours import WEEKDAY_NAMES
from emporio.store.domain.info import EMPORIO

_VERIFY_MSG = "Para consultar o pedido preciso confirmar a identidade: peça o e-mail ou o telefone cadastrado na compra."
_FAILED_MSG = (
    "Não foi possível confirmar o pedido com os dados informados (número do pedido e e-mail/telefone "
    "precisam corresponder ao cadastro). Não revele se o pedido existe."
)
_OUTCOME_LABELS = {
    ReturnOutcome.ELIGIBLE: "elegível",
    ReturnOutcome.NOT_ELIGIBLE: "não elegível",
    ReturnOutcome.MANUFACTURER_WARRANTY: "fora do prazo de troca na loja — garantia do fabricante",
    ReturnOutcome.NOT_YET_RECEIVED: "pedido ainda não recebido",
}


def _promotion_view(promotion: Promotion) -> PromotionView:
    return PromotionView(
        name=promotion.description,
        discount=f"{promotion.discount_percent.normalize():f}%",
        active=promotion.is_active,
    )


def product_view(offer: ProductOffer) -> ProductView:
    product, quote = offer.product, offer.quote
    if quote.pix_discount_applies:
        pix_note = f"{PIX_DISCOUNT_PERCENT}% de desconto no PIX sobre o preço de tabela"
    else:
        pix_note = "produto em promoção: o desconto do PIX não se acumula com a promoção"
    return ProductView(
        id=product.id,
        name=product.name,
        category=offer.category,
        description=product.description,
        availability=product.availability.label,
        in_stock_units=product.stock_quantity if product.is_sellable else 0,
        list_price=quote.list_price.format(),
        promotion=_promotion_view(quote.active_promotion) if quote.active_promotion else None,
        promotional_price=quote.final_price.format() if quote.active_promotion else None,
        pix_price=quote.pix_price.format(),
        pix_note=pix_note,
        max_installments=f"até {max_installments(quote.final_price)}x sem juros",
        specs=readable_specs(product.specs),
    )


async def search_products(args: SearchProductsArgs, ctx: ToolContext) -> View:
    result = await ctx.services.catalog.search(
        SearchCriteria(
            query=args.query,
            category=args.category,
            min_price=Decimal(str(args.min_price)) if args.min_price is not None else None,
            max_price=Decimal(str(args.max_price)) if args.max_price is not None else None,
            in_stock_only=args.in_stock_only,
            strings=args.strings,
            electric=args.electric,
            limit=args.limit,
        )
    )
    note = None
    if result.out_of_catalog:
        note = (
            f"'{result.out_of_catalog}' é um acessório. A loja trabalha exclusivamente com instrumentos musicais "
            f"e não vende {', '.join(EMPORIO.does_not_sell)}. Redirecione com gentileza."
        )
    elif result.unknown_category:
        note = f"Categoria '{result.unknown_category}' não existe no catálogo."
    elif result.empty_category:
        note = f"Não há produtos de '{result.empty_category}' no catálogo no momento."
    elif not result.offers:
        note = "Nenhum produto atende exatamente aos critérios; as alternativas abaixo são as mais próximas em estoque."
    return SearchProductsView(
        results=[product_view(o) for o in result.offers],
        alternatives=[product_view(o) for o in result.alternatives],
        note=note,
    )


async def get_product(args: GetProductArgs, ctx: ToolContext) -> View:
    try:
        details = await ctx.services.catalog.get_product(args.product_ref)
    except NotFoundError:
        return ErrorView(
            error=f"Nenhum produto encontrado para '{args.product_ref}'. Use search_products."
        )
    note = None
    if details.offer is None:
        note = "Mais de um produto corresponde ao nome; confirme com o cliente qual deles."
    elif not details.offer.product.is_sellable:
        note = "Produto indisponível para venda: informe e ofereça as alternativas."
    return ProductDetailsView(
        product=product_view(details.offer) if details.offer else None,
        expired_promotions=[_promotion_view(p) for p in details.expired_promotions],
        alternatives=[product_view(o) for o in details.alternatives],
        ambiguous_candidates=[product_view(o) for o in details.candidates],
        note=note,
    )


async def calculate_payment_options(args: PaymentOptionsArgs, ctx: ToolContext) -> View:
    try:
        options = await ctx.services.catalog.payment_options(
            product_id=args.product_id,
            amount=Decimal(str(args.amount)) if args.amount is not None else None,
            installments=args.installments,
        )
    except (NotFoundError, ValueError) as exc:
        return ErrorView(error=str(exc))
    requested = options.requested.reason if options.requested else None
    if options.pix_discount_applies:
        pix_note = f"PIX à vista com {PIX_DISCOUNT_PERCENT}% de desconto sobre o preço de tabela."
    else:
        pix_note = (
            "Preço promocional: o desconto do PIX não se aplica sobre preços já promocionais."
        )
    return PaymentOptionsView(
        product=options.offer.product.name if options.offer else None,
        card_total=options.card_total.format(),
        pix_total=options.pix_total.format(),
        pix_note=pix_note,
        installments=[
            InstallmentView(
                count=o.count, installment=o.installment_value.format(), total=o.total.format()
            )
            for o in options.installments
        ],
        requested_installments=requested,
        combined_payment=(
            "permitido (ex.: PIX + cartão), pois a compra é acima de R$ 2.000,00"
            if options.combined_payment_allowed
            else "não disponível: combinar formas de pagamento só é permitido acima de R$ 2.000,00"
        ),
        other_methods=[
            "cartão de débito à vista (todas as bandeiras)",
            "boleto bancário à vista (compensação em até 3 dias úteis)",
        ],
    )


def _verification_message(lookup: OrderLookup) -> str | None:
    if lookup.verification is Verification.MISSING_IDENTITY:
        return _VERIFY_MSG
    if lookup.verification is Verification.FAILED:
        return _FAILED_MSG
    return None


async def get_order_status(args: OrderLookupArgs, ctx: ToolContext) -> View:
    lookup = await ctx.services.orders.lookup(args.order_id, email=args.email, phone=args.phone)
    if lookup.order is None or lookup.customer is None:
        return OrderStatusView(verified=False, message=_verification_message(lookup))
    ctx.verified_contacts.update({lookup.customer.email, lookup.customer.phone})
    order = lookup.order
    tracking_note = None
    if order.tracking_code:
        tracking_note = "Rastreie no site dos Correios ou da Jadlog com este código."
    elif order.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
        tracking_note = "O código de rastreamento é enviado por e-mail e WhatsApp assim que o pedido for despachado."
    return OrderStatusView(
        verified=True,
        message=None,
        order_id=order.id,
        customer_first_name=lookup.customer.first_name,
        status=order.status.label,
        order_date=f"{order.order_date:%d/%m/%Y}",
        total=order.total.format(),
        payment=order.payment.label,
        items=[
            OrderItemView(product=line.product_name, quantity=line.quantity)
            for line in lookup.lines
        ],
        tracking_code=order.tracking_code,
        tracking_note=tracking_note,
        estimated_delivery=f"{order.estimated_delivery:%d/%m/%Y}"
        if order.estimated_delivery
        else None,
        notes=order.notes,
    )


async def check_return_eligibility(args: ReturnEligibilityArgs, ctx: ToolContext) -> View:
    check = await ctx.services.orders.check_return(
        args.order_id, ReturnReason(args.reason), email=args.email, phone=args.phone
    )
    decision, lookup = check.decision, check.lookup
    if decision is None or lookup.customer is None:
        return ReturnEligibilityView(verified=False, message=_verification_message(lookup))
    ctx.verified_contacts.update({lookup.customer.email, lookup.customer.phone})
    return ReturnEligibilityView(
        verified=True,
        message=None,
        order_id=args.order_id,
        outcome=_OUTCOME_LABELS[decision.outcome],
        explanation=decision.explanation,
        policy_section=decision.policy_section,
        window_start=f"{decision.window_start:%d/%m/%Y}" if decision.window_start else None,
        deadline=f"{decision.deadline:%d/%m/%Y}" if decision.deadline else None,
        days_elapsed=decision.days_elapsed,
        conditions=list(decision.conditions),
        next_steps=list(decision.next_steps),
        never_eligible_items=list(decision.exclusions),
        reference_date=f"{ctx.services.clock.today():%d/%m/%Y}",
    )


async def estimate_shipping(args: ShippingArgs, ctx: ToolContext) -> View:
    quote = ctx.services.store.shipping(args.city, Money.of(Decimal(str(args.order_value))))
    if quote.fee is None:
        fee = "calculado pelo CEP de destino, peso e dimensões (não há valor fixo)"
    elif quote.free_shipping:
        fee = "grátis (pedido acima de R$ 500,00)"
    else:
        fee = f"{quote.fee.format()} (taxa fixa para pedidos de até R$ 500,00)"
    return ShippingView(
        city=quote.city,
        metro_region=quote.metro_region,
        fee=fee,
        options=[
            ShippingOptionView(carrier=o.carrier, estimated_days=o.estimated_days)
            for o in quote.options
        ],
        notes=list(quote.notes),
    )


async def get_store_status(args: StoreStatusArgs, ctx: ToolContext) -> View:
    status = ctx.services.store.status()
    now = status.now
    next_opening = None
    if status.next_opening:
        next_opening = (
            f"{WEEKDAY_NAMES[status.next_opening.weekday()]}, {status.next_opening:%d/%m às %H:%M}"
        )
    return StoreStatusView(
        now=f"{WEEKDAY_NAMES[now.weekday()]}, {now:%d/%m/%Y %H:%M}",
        is_open=status.is_open,
        closed_reason=status.closed_reason,
        next_opening=next_opening,
        hours=[
            "segunda a sexta: 09:00 às 18:00",
            "sábado: 09:00 às 13:00",
            "domingos e feriados: fechado",
        ],
        address=EMPORIO.address,
        phone=EMPORIO.phone,
        whatsapp=EMPORIO.whatsapp,
        email=EMPORIO.email,
        holidays_note="Em datas especiais (Black Friday, aniversário da loja, Natal) o horário pode ser estendido.",
    )


async def search_policies(args: SearchPoliciesArgs, ctx: ToolContext) -> View:
    hits = await ctx.services.policies.search(args.query, k=4)
    ctx.cited_sections.update(hit.section_path for hit in hits)
    return SearchPoliciesView(
        hits=[PolicyHitView(section=h.section_path, text=h.content) for h in hits]
    )


async def open_support_ticket(args: OpenTicketArgs, ctx: ToolContext) -> View:
    ticket = await ctx.services.tickets.open(
        TicketType(args.type), args.summary, args.contact, ctx.conversation_id
    )
    ctx.ticket_protocols.append(ticket.protocol)
    return TicketView(protocol=ticket.protocol, type=ticket.type.label, response_time=RESPONSE_SLA)
