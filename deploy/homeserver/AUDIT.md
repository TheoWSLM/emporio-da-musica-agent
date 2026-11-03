# Deployment audit

What the application needs from a host, checked before deploying it next to other apps.

| Item | This application |
|---|---|
| Runtime | Python 3.13 (API, `uvicorn`), Caddy 2 (edge: static Vue build + `/api` proxy), PostgreSQL 16 + pgvector |
| Exposure | Only the edge container. Published on `127.0.0.1:${EDGE_PORT}` for local checks and joined to the host's existing ingress network (alias `emporio-musica-caddy`) so the existing Cloudflare tunnel connector can reach it. No port is opened on the router; TLS ends at Cloudflare. |
| API | Not published, not on the ingress network. Trusts `X-Forwarded-For` only because Caddy is its sole client. |
| Database | Dedicated Postgres container, no published port, data in `data/postgres/` (bind mount). |
| Uploads / files | None. |
| Queues / workers / cron | None. Two one-shot jobs on every start: `migrate` (Alembic) and `ingest` (idempotent; skips when inputs are unchanged). |
| Secrets | `OPENAI_API_KEY` (required), `TYPESAFE_API_KEY` (optional), `POSTGRES_PASSWORD`. Only in `.env` (mode 600) on the host. |
| Persistence | Catalog, orders and policy embeddings are rebuilt from `data/raw/` by `ingest`. Only `conversations`, `messages` and `support_tickets` are runtime data (see `scripts/backup.sh`). |
| Resources | Postgres 512 MB / 1 CPU, API 768 MB / 2 CPU, Caddy 128 MB / 1 CPU; containers run as UID 1000 where possible, `no-new-privileges`, `cap_drop: ALL`, log rotation. |
| Outbound | `api.openai.com` and, if enabled, `api.typesafe.ai`. |
| Abuse protection | Per-IP sliding window, per-conversation turn cap and global daily budget (HTTP 429); 2,000-character messages; request body limit at the edge. |
