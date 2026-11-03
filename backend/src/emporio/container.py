"""Composition root: the only place that knows which adapter implements which port."""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from emporio.assistant.classification.jev import JevClient, JevInputClassifier, JevOutputClassifier
from emporio.assistant.classification.openai import OpenAIInputClassifier, OpenAIOutputClassifier
from emporio.assistant.classification.ports import InputClassifier, OutputClassifier
from emporio.assistant.graph import AgentConfig, Assistant
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
    assistant: Assistant
    jev: JevClient | None = None

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
        services = build_services(sessions, embedder, clock)
        conversations = SqlConversationStore(sessions)
        input_classifier: InputClassifier = OpenAIInputClassifier(client, settings.classifier_model)
        output_classifier: OutputClassifier = OpenAIOutputClassifier(
            client, settings.classifier_model
        )
        jev = None
        if settings.jev_enabled and settings.typesafe_api_key is not None:
            jev = JevClient(
                settings.typesafe_api_key.get_secret_value(),
                settings.jev_model,
                settings.jev_timeout_seconds,
            )
            input_classifier = JevInputClassifier(jev, fallback=input_classifier)
            output_classifier = JevOutputClassifier(jev, fallback=output_classifier)
        assistant = Assistant(
            client=client,
            services=services,
            conversations=conversations,
            input_classifier=input_classifier,
            output_classifier=output_classifier,
            config=AgentConfig(
                model=settings.agent_model,
                reasoning_effort=settings.agent_reasoning_effort,
                max_output_tokens=settings.agent_max_output_tokens,
                max_tool_rounds=settings.agent_max_tool_rounds,
                history_window=settings.history_window,
                output_review=settings.output_review,
            ),
        )
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            openai=client,
            embedder=embedder,
            clock=clock,
            services=services,
            conversations=conversations,
            assistant=assistant,
            jev=jev,
        )

    async def close(self) -> None:
        if self.jev is not None:
            await self.jev.close()
        await self.openai.close()
        await self.engine.dispose()
