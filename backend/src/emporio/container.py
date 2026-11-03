"""Composition root: the only place that knows which adapter implements which port."""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from emporio.assistant.tools.context import Services
from emporio.catalog.application.use_cases import CatalogService
from emporio.catalog.infrastructure.repositories import (
    SqlCategoryReader,
    SqlProductReader,
    SqlPromotionReader,
)
from emporio.config import Settings
from emporio.conversation.infrastructure.repositories import SqlConversationStore, SqlTicketStore
from emporio.infrastructure.db import create_engine, create_session_factory
from emporio.knowledge.application.ports import Embedder
from emporio.knowledge.infrastructure.embedders import OpenAIEmbedder
from emporio.knowledge.infrastructure.retriever import SqlPolicyRetriever
from emporio.orders.application.use_cases import OrderService
from emporio.orders.infrastructure.repositories import SqlCustomerReader, SqlOrderReader
from emporio.shared.clock import Clock, ReferenceDateClock, SystemClock
from emporio.store.application.use_cases import StoreService


def build_clock(settings: Settings) -> Clock:
    if settings.app_reference_date is not None:
        return ReferenceDateClock(settings.app_reference_date, settings.app_timezone)
    return SystemClock(settings.app_timezone)


def build_services(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, clock: Clock
) -> Services:
    products = SqlProductReader(sessions)
    return Services(
        catalog=CatalogService(
            products, SqlPromotionReader(sessions), SqlCategoryReader(sessions), embedder
        ),
        orders=OrderService(SqlOrderReader(sessions), SqlCustomerReader(sessions), products, clock),
        store=StoreService(clock),
        policies=SqlPolicyRetriever(sessions, embedder),
        tickets=SqlTicketStore(sessions, clock),
        clock=clock,
    )


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    openai: AsyncOpenAI
    embedder: Embedder
    clock: Clock
    services: Services
    conversations: SqlConversationStore

    @classmethod
    def build(cls, settings: Settings) -> Container:
        if settings.openai_api_key is None:
            raise RuntimeError("OPENAI_API_KEY is required (see .env.example)")
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(), max_retries=2, timeout=60
        )
        embedder = OpenAIEmbedder(client, settings.embedding_model, settings.embedding_dimensions)
        clock = build_clock(settings)
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            openai=client,
            embedder=embedder,
            clock=clock,
            services=build_services(sessions, embedder, clock),
            conversations=SqlConversationStore(sessions),
        )

    async def close(self) -> None:
        await self.openai.close()
        await self.engine.dispose()
