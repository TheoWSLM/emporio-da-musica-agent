"""Tool contracts. Args are sent to OpenAI as strict JSON schemas; views are what the model reads.

Views are compact and *ready to communicate*: money is pre-formatted (R$ 1.234,56), statuses are
already PT-BR labels, so the model never has to compute or translate a business fact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class View(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- arguments


class SearchProductsArgs(Args):
    query: str | None = Field(
        description="What the customer is looking for, in their words (e.g. 'violão para iniciante com som quente'). Null to list by filters only."
    )
    category: str | None = Field(
        description="Instrument category in Portuguese if the customer named one (e.g. 'violão', 'guitarra', 'ukulele', 'baixo', 'bateria', 'teclado')."
    )
    min_price: float | None = Field(description="Minimum list price in BRL.", ge=0)
    max_price: float | None = Field(
        description="Maximum list price in BRL (e.g. 'até R$1000' -> 1000).", ge=0
    )
    strings: Literal["nylon", "steel"] | None = Field(
        description="String type for violões/ukuleles."
    )
    electric: bool | None = Field(
        description="True for electro-acoustic (with pickup), false for purely acoustic."
    )
    in_stock_only: bool = Field(
        description="Only products available for sale now. Use true unless the customer asks about the whole catalog."
    )
    limit: int = Field(description="How many products to return (1-8).", ge=1, le=8)


class GetProductArgs(Args):
    product_ref: str = Field(
        description="Product id or (approximate) product name as the customer wrote it, e.g. 'Takamine GD20'."
    )


class PaymentOptionsArgs(Args):
    product_id: int | None = Field(
        description="Product id when the question is about a specific product."
    )
    amount: float | None = Field(
        description="Purchase amount in BRL when there is no single product (e.g. a cart total).",
        gt=0,
    )
    installments: int | None = Field(
        description="Number of installments the customer asked about, if any (1-12).", ge=1, le=24
    )


class OrderLookupArgs(Args):
    order_id: int = Field(description="Order number given by the customer.", gt=0)
    email: str | None = Field(description="E-mail the customer provided to confirm identity.")
    phone: str | None = Field(description="Phone the customer provided to confirm identity.")


class ReturnEligibilityArgs(OrderLookupArgs):
    reason: Literal["regret", "defect", "preference"] = Field(
        description="regret = gave up the purchase / 'me arrependi'; defect = manufacturing defect; preference = exchange for another colour/model/size."
    )


class ShippingArgs(Args):
    city: str = Field(description="Destination city.")
    order_value: float = Field(
        description="Order value in BRL used for the free-shipping rule.", gt=0
    )


class StoreStatusArgs(Args):
    pass


class SearchPoliciesArgs(Args):
    query: str = Field(description="The policy question, in Portuguese.")


class OpenTicketArgs(Args):
    type: Literal["complaint", "exchange", "human"] = Field(
        description="complaint = reclamação; exchange = troca/devolução that needs the team; human = customer wants a human agent."
    )
    summary: str = Field(
        description="Short summary of the case in Portuguese, with order number if any.",
        max_length=600,
    )
    contact: str | None = Field(
        description="Contact (e-mail or phone) the customer provided, if any."
    )


# ---------------------------------------------------------------- views


class ErrorView(View):
    error: str


class PromotionView(View):
    name: str
    discount: str
    active: bool


class ProductView(View):
    id: int
    name: str
    category: str
    description: str
    availability: str
    in_stock_units: int
    list_price: str
    promotion: PromotionView | None
    promotional_price: str | None
    pix_price: str
    pix_note: str
    max_installments: str
    specs: list[str]


class SearchProductsView(View):
    results: list[ProductView]
    alternatives: list[ProductView]
    note: str | None


class ProductDetailsView(View):
    product: ProductView | None
    expired_promotions: list[PromotionView]
    alternatives: list[ProductView]
    ambiguous_candidates: list[ProductView]
    note: str | None


class InstallmentView(View):
    count: int
    installment: str
    total: str


class PaymentOptionsView(View):
    product: str | None
    card_total: str
    pix_total: str
    pix_note: str
    installments: list[InstallmentView]
    requested_installments: str | None
    combined_payment: str
    other_methods: list[str]


class OrderItemView(View):
    product: str
    quantity: int


class OrderStatusView(View):
    verified: bool
    message: str | None
    order_id: int | None = None
    customer_first_name: str | None = None
    status: str | None = None
    order_date: str | None = None
    total: str | None = None
    payment: str | None = None
    items: list[OrderItemView] = []
    tracking_code: str | None = None
    tracking_note: str | None = None
    estimated_delivery: str | None = None
    notes: str | None = None


class ReturnEligibilityView(View):
    verified: bool
    message: str | None
    order_id: int | None = None
    outcome: str | None = None
    explanation: str | None = None
    policy_section: str | None = None
    window_start: str | None = None
    deadline: str | None = None
    days_elapsed: int | None = None
    conditions: list[str] = []
    next_steps: list[str] = []
    never_eligible_items: list[str] = []
    reference_date: str | None = None


class ShippingOptionView(View):
    carrier: str
    estimated_days: str


class ShippingView(View):
    city: str
    metro_region: bool
    fee: str
    options: list[ShippingOptionView]
    notes: list[str]


class StoreStatusView(View):
    now: str
    is_open: bool
    closed_reason: str | None
    next_opening: str | None
    hours: list[str]
    address: str
    phone: str
    whatsapp: str
    email: str
    holidays_note: str


class PolicyHitView(View):
    section: str
    text: str


class SearchPoliciesView(View):
    hits: list[PolicyHitView]


class TicketView(View):
    protocol: str
    type: str
    response_time: str
