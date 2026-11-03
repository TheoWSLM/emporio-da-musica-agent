"""Per-turn context shared by the tools (services + facts the guardrails need)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from emporio.catalog.application.use_cases import CatalogService
from emporio.conversation.application.ports import TicketStore
from emporio.knowledge.application.ports import PolicyRetriever
from emporio.orders.application.use_cases import OrderService
from emporio.shared.clock import Clock
from emporio.store.application.use_cases import StoreService


@dataclass(frozen=True)
class Services:
    catalog: CatalogService
    orders: OrderService
    store: StoreService
    policies: PolicyRetriever
    tickets: TicketStore
    clock: Clock


@dataclass
class ToolContext:
    services: Services
    conversation_id: uuid.UUID | None = None
    verified_contacts: set[str] = field(default_factory=set)
    """Contacts of customers verified in this turn — the only personal data the reply may contain."""
    cited_sections: set[str] = field(default_factory=set)
    ticket_protocols: list[str] = field(default_factory=list)
