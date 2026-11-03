SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&

.DEFAULT_GOAL := help
.PHONY: help up down logs ps ingest chat test test-unit lint fmt typecheck eval examples reset

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example — fill in OPENAI_API_KEY and run 'make up' again."
	@exit 1

up: .env ## Build and start the whole stack (DB, migrations, ingestion, API, web)
	@mkdir -p data/postgres
	$(COMPOSE) up -d --build
	@echo "UI:  http://127.0.0.1:$${EDGE_PORT:-18082}"

down: ## Stop the stack (keeps the database)
	$(COMPOSE) down

logs: ## Follow API logs
	$(COMPOSE) logs -f api

ps: ## Show service status
	$(COMPOSE) ps

ingest: ## Re-run the (idempotent) data ingestion
	$(COMPOSE) run --rm ingest

chat: ## Talk to the agent in the terminal
	$(COMPOSE) run --rm -it api emporio chat

test: ## Unit + graph tests, plus integration tests when the DB is up
	$(BACKEND) uv run pytest -q

test-unit: ## Fast tests only (no database, no network)
	$(BACKEND) uv run pytest -q -m "not integration and not evals"

lint: ## Ruff + mypy
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy

fmt: ## Auto-format
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .

eval: ## Golden-set evaluation against the real models (needs OPENAI_API_KEY)
	$(COMPOSE) run --rm api emporio eval

examples: ## Regenerate the example conversations in examples/conversations
	$(COMPOSE) run --rm -v ./examples:/app/examples api emporio examples

reset: ## Destroy the database volume (data is re-ingested on next 'make up')
	$(COMPOSE) down
	rm -rf data/postgres
