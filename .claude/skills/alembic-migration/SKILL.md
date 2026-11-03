---
name: alembic-migration
description: How to create and review Alembic migrations for this project, including pgvector HNSW, pg_trgm and full-text indexes. Use when the database schema changes.
---
# Alembic migrations

- Create: `cd backend && uv run alembic revision --autogenerate -m "<what>"` with the compose DB up
  (`DATABASE_URL=postgresql+psycopg://emporio:emporio@127.0.0.1:<port>/emporio`).
- **Always review by hand**: autogenerate does not emit `CREATE EXTENSION`, HNSW (`postgresql_using="hnsw"`,
  `postgresql_ops={"embedding": "vector_cosine_ops"}`), GIN trigram (`gin_trgm_ops`) or generated
  `tsvector` columns correctly — write those explicitly with `op.execute`/`op.create_index`.
- Every migration must have a working `downgrade()`.
- Migrations run automatically on `make up` (one-shot `migrate` service) and must be idempotent across
  restarts — never put data loading in a migration (that belongs to `ingest`).
