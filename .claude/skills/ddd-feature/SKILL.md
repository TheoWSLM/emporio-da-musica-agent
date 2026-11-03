---
name: ddd-feature
description: Recipe for adding a business capability (new rule or use case) to a bounded context while respecting the dependency rule. Use when adding or changing domain behaviour in catalog, orders, store, knowledge or conversation.
---
# Adding a feature to a bounded context

1. **Domain first** (`<context>/domain/`): model the rule as a frozen dataclass / enum / pure function or
   domain service. No I/O, no Pydantic, no framework imports. Money is `Money`, time comes as an argument.
2. **Unit tests** (`tests/unit/<context>/`): cover the edges named in the store manual (e.g. day 7 vs 8,
   installment minimums R$50/80/100). Run `make test-unit`.
3. **Port** (`<context>/application/ports.py`): a small `Protocol` describing only what the use case needs
   (`ProductReader`, `OrderReader`...). Interface segregation over one big repository.
4. **Use case** (`<context>/application/`): one public method per intention on the context's service class
   (`CatalogService`, `OrderService`, `StoreService`). It
   orchestrates ports + domain, returns domain objects or small result dataclasses.
5. **Adapter** (`<context>/infrastructure/`): SQLAlchemy/pgvector/OpenAI implementation of the port.
   Integration test with the compose Postgres (`@pytest.mark.integration`).
6. **Wire** it in `emporio/container.py` (the only composition root).

Checklist: `grep -r "infrastructure\|fastapi\|pydantic" src/emporio/<context>/domain` must be empty.
