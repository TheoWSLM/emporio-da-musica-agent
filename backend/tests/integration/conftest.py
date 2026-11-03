"""Integration fixtures: a migrated and ingested test database (compose service `postgres-test`)."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.infrastructure.db import create_engine, create_session_factory
from emporio.ingestion.pipeline import ingest_structured

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR.parent / "data" / "raw"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://emporio:emporio@127.0.0.1:15432/emporio_test"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(
            "test database not available (run: docker compose --profile dev up -d postgres-test)"
        )
    await asyncio.to_thread(
        subprocess.run,
        ["alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
        capture_output=True,
    )
    factory = create_session_factory(engine)
    await ingest_structured(factory, DATA_DIR, force=True)
    yield factory
    await engine.dispose()
